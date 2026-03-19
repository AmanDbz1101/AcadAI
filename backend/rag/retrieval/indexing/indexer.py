"""
Document indexer.

Orchestrates the full ingestion pipeline:
    chunks → dense embed → sparse embed → upsert to Qdrant

One BM25 encoder is fitted **per document** (using only that document's
chunks as corpus) and saved to disk so it can be reloaded at query time
without re-fitting from scratch.  This avoids the problem of a global
vocabulary that drifts as new documents are added.

For multi-document collections a *global* BM25 encoder is more accurate,
but per-document encoders are simpler to manage and work well in practice
for a retrieval-augmented setting where queries usually target a specific
paper.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rag.retrieval.chunking.models import Chunk
from rag.retrieval.chunking.section_chunker import SectionChunker
from rag.retrieval.config import BM25_ENCODER_DIR, OUTPUT_DIR

logger = logging.getLogger(__name__)

# Qdrant batch upsert size
_UPSERT_BATCH = 64


@dataclass
class IndexingResult:
    """Summary returned after a successful indexing run."""

    document_id: str
    collection_name: str
    total_chunks: int
    bm25_encoder_path: str
    duration_seconds: float
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)


class Indexer:
    """
    Embeds and upserts document chunks into Qdrant.

    Parameters
    ----------
    store_manager : QdrantStoreManager
        Manages the target Qdrant collection.
    dense_encoder : DenseEncoder
        Encodes chunk content to dense (384-dim) vectors.
    sparse_encoder_cls : type, optional
        Class of the sparse encoder to instantiate per document.
        Defaults to :class:`~rag.retrieval.embeddings.BM25SparseEncoder`.
    output_dir : Path, optional
        Directory where BM25 encoder pickles are written.
    """

    def __init__(
        self,
        store_manager,
        dense_encoder,
        sparse_encoder_cls=None,
        output_dir: Optional[Path] = None,
    ) -> None:
        self.store_manager = store_manager
        self.dense_encoder = dense_encoder
        self._sparse_encoder_cls = sparse_encoder_cls
        self.output_dir = output_dir or OUTPUT_DIR
        self._chunker = SectionChunker()

    def _resolve_sparse_cls(self):
        if self._sparse_encoder_cls is not None:
            return self._sparse_encoder_cls
        from rag.retrieval.embeddings.sparse_encoder import BM25SparseEncoder

        return BM25SparseEncoder

    # ── Main entry point ──────────────────────────────────────────────────────

    def index_document(
        self,
        hierarchy_json_path: Path,
        output_dir: Optional[Path] = None,
        pdf_path: Optional[Path] = None,
        force_reindex: bool = False,
    ) -> IndexingResult:
        """
        Index a document into Qdrant.

        Parameters
        ----------
        hierarchy_json_path : Path
            Path to the ``<document_id>_hierarchy.json`` artifact.
        output_dir : Path, optional
            Directory that contains the document's output artifacts.
            Defaults to the parent of *hierarchy_json_path*.
        pdf_path : Path, optional
            Original PDF.  When provided, PyMuPDF yields per-page text
            (more accurate section boundaries).
        force_reindex : bool
            Skip the "already indexed" check and re-upsert all points.

        Returns
        -------
        IndexingResult
        """
        t0 = time.time()
        hierarchy_json_path = Path(hierarchy_json_path)
        doc_output_dir = output_dir or hierarchy_json_path.parent

        # ── Derive document_id ────────────────────────────────────────────────
        with open(hierarchy_json_path, encoding="utf-8") as f:
            raw = json.load(f)
        hier = raw.get("hierarchy", raw)
        document_id: str = hier.get("document_id", "")
        if not document_id:
            raise ValueError(
                f"Could not read document_id from {hierarchy_json_path}"
            )

        # ── Skip if already indexed ───────────────────────────────────────────
        if not force_reindex and self.store_manager.document_is_indexed(document_id):
            logger.info(
                "Indexer: document %s already indexed in '%s' — skipping",
                document_id,
                self.store_manager.collection_name,
            )
            bm25_path = self.output_dir / f"{document_id}_bm25.pkl"
            return IndexingResult(
                document_id=document_id,
                collection_name=self.store_manager.collection_name,
                total_chunks=0,
                bm25_encoder_path=str(bm25_path),
                duration_seconds=0.0,
                skipped=True,
            )

        # ── Ensure collection exists ──────────────────────────────────────────
        self.store_manager.create_collection()

        # ── Remove any existing points for this document before re-indexing ──
        # (prevents duplicate chunks when the same file is processed again)
        self.store_manager.delete_document_points(document_id)

        # ── Chunk the document ────────────────────────────────────────────────
        chunks: list[Chunk] = self._chunker.chunk_document(
            hierarchy_json_path=hierarchy_json_path,
            output_dir=doc_output_dir,
            pdf_path=pdf_path,
        )

        # Persist section-title lookup used by section-scoped retrieval.
        self._write_section_lookup(document_id=document_id, chunks=chunks)

        if not chunks:
            logger.warning("Indexer: no chunks produced for document %s", document_id)
            return IndexingResult(
                document_id=document_id,
                collection_name=self.store_manager.collection_name,
                total_chunks=0,
                bm25_encoder_path="",
                duration_seconds=time.time() - t0,
                warnings=["No chunks produced — document may have empty sections"],
            )

        corpus = [c.content for c in chunks]

        # ── Fit and save BM25 encoder ─────────────────────────────────────────
        BM25Cls = self._resolve_sparse_cls()
        sparse_enc = BM25Cls()
        sparse_enc.fit(corpus)

        bm25_path = self.output_dir / f"{document_id}_bm25.pkl"
        sparse_enc.save(bm25_path)
        logger.info("Indexer: BM25 encoder saved to %s", bm25_path)

        # ── Embed ─────────────────────────────────────────────────────────────
        logger.info("Indexer: encoding %d chunks …", len(chunks))
        dense_vecs = self.dense_encoder.encode_documents(corpus)
        sparse_vecs = sparse_enc.embed_documents(corpus)

        # ── Upsert to Qdrant ──────────────────────────────────────────────────
        self._upsert_batches(chunks, dense_vecs, sparse_vecs)

        duration = time.time() - t0
        logger.info(
            "Indexer: indexed %d chunks for document %s in %.1fs",
            len(chunks),
            document_id,
            duration,
        )

        return IndexingResult(
            document_id=document_id,
            collection_name=self.store_manager.collection_name,
            total_chunks=len(chunks),
            bm25_encoder_path=str(bm25_path),
            duration_seconds=duration,
        )

    # ── Batch upsert ──────────────────────────────────────────────────────────

    def _upsert_batches(
        self,
        chunks: list[Chunk],
        dense_vecs,   # np.ndarray (N, D)
        sparse_vecs,  # list[SparseVector]
    ) -> None:
        from qdrant_client.models import PointStruct, SparseVector  # type: ignore
        from rag.retrieval.config import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME

        client = self.store_manager.client
        collection = self.store_manager.collection_name
        total = len(chunks)

        for batch_start in range(0, total, _UPSERT_BATCH):
            batch_end = min(batch_start + _UPSERT_BATCH, total)
            points = []
            for i in range(batch_start, batch_end):
                sv = sparse_vecs[i]
                # Deterministic UUID: same document + same chunk index → same ID.
                # This ensures Qdrant upsert overwrites rather than duplicates.
                chunk_uuid = str(
                    uuid.uuid5(uuid.NAMESPACE_DNS, f"{chunks[i].document_id}:{i}")
                )
                points.append(
                    PointStruct(
                        id=chunk_uuid,
                        payload=chunks[i].to_payload(),
                        vector={
                            DENSE_VECTOR_NAME: dense_vecs[i].tolist(),
                            SPARSE_VECTOR_NAME: {
                                "indices": sv.indices,
                                "values": sv.values,
                            },
                        },
                    )
                )

            client.upsert(
                collection_name=collection,
                points=points,
                wait=True,
            )
            logger.debug(
                "Indexer: upserted batch %d–%d / %d",
                batch_start,
                batch_end - 1,
                total,
            )

    def _write_section_lookup(self, document_id: str, chunks: list[Chunk]) -> None:
        """
        Persist a normalized section lookup sidecar:
            {normalized_section_title: [original_title_variants...]}

        The retrieval graph uses this to translate guide section names into
        payload filter values for ``section_path``.
        """
        lookup: dict[str, set[str]] = {}

        for chunk in chunks:
            titles = list(chunk.section_path or [])
            if chunk.section_title:
                titles.append(chunk.section_title)

            for title in titles:
                if not title:
                    continue
                norm = " ".join(title.lower().split())
                lookup.setdefault(norm, set()).add(title)

        serializable = {k: sorted(v) for k, v in lookup.items()}
        out_path = self.output_dir / f"{document_id}_sections.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)

        logger.info(
            "Indexer: section lookup saved to %s (%d normalized keys)",
            out_path,
            len(serializable),
        )
