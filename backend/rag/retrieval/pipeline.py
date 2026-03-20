"""
RetrievalPipeline — top-level orchestrator.

Composes chunking, dense + sparse encoding, Qdrant indexing, hybrid
retrieval, and FlashRank reranking into a single object that the LangGraph
``retriever_node`` (and other callers) can use without knowing the internals.

Typical usage
-------------
::

    from rag.retrieval import RetrievalPipeline

    pipeline = RetrievalPipeline()

    # --- indexing (call once per document) ---
    result = pipeline.index(
        hierarchy_json_path=Path("output/<id>_hierarchy.json"),
        pdf_path=Path("uploads/paper.pdf"),   # optional but improves accuracy
    )
    print(f"Indexed {result.total_chunks} chunks")

    # --- retrieval ---
    hits = pipeline.query(
        query="How does multi-head attention work?",
        document_id="<id>",
        top_k=20,
        top_n=5,
    )
    for h in hits:
        print(h.score, h.metadata["section_title"], h.content[:120])

Singletons
----------
``RetrievalPipeline`` is designed to be instantiated **once** per process and
shared.  The dense encoder model is loaded lazily on first use; subsequent
calls are fast.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from rag.retrieval.config import (
    OUTPUT_DIR,
    RETRIEVER_TOP_K,
    RERANKER_TOP_N,
)

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """
    All-in-one hybrid retrieval pipeline.

    Parameters
    ----------
    collection_name : str, optional
        Qdrant collection name.  Defaults to ``QDRANT_COLLECTION_NAME``.
    dense_model : str, optional
        HuggingFace model for dense embeddings.
    output_dir : Path, optional
        Where BM25 encoder pickles live.
    enable_reranking : bool
        Set to False to skip FlashRank (useful when flashrank is not installed
        or in memory-constrained environments).
    """

    def __init__(
        self,
        collection_name: Optional[str] = None,
        dense_model: Optional[str] = None,
        output_dir: Optional[Path] = None,
        enable_reranking: bool = True,
    ) -> None:
        self._collection_name = collection_name
        self._dense_model = dense_model
        self._output_dir = output_dir or OUTPUT_DIR
        self._enable_reranking = enable_reranking

        # Lazy component references (initialised on first use)
        self._store_manager = None
        self._dense_encoder = None
        self._indexer = None
        self._reranker = None

        # Cache of loaded BM25 encoders keyed by document_id
        self._bm25_cache: dict[str, object] = {}

    # ── Lazy component accessors ──────────────────────────────────────────────

    def _get_store_manager(self):
        if self._store_manager is None:
            from rag.retrieval.indexing.qdrant_store import QdrantStoreManager

            self._store_manager = QdrantStoreManager(
                collection_name=self._collection_name
            )
        return self._store_manager

    def _get_dense_encoder(self):
        if self._dense_encoder is None:
            from rag.retrieval.embeddings.dense_encoder import DenseEncoder
            from rag.retrieval.config import DENSE_MODEL

            self._dense_encoder = DenseEncoder(
                model_name=self._dense_model or DENSE_MODEL
            )
        return self._dense_encoder

    def _get_indexer(self):
        if self._indexer is None:
            from rag.retrieval.indexing.indexer import Indexer

            self._indexer = Indexer(
                store_manager=self._get_store_manager(),
                dense_encoder=self._get_dense_encoder(),
                output_dir=self._output_dir,
            )
        return self._indexer

    def _get_reranker(self):
        if not self._enable_reranking:
            return None
        if self._reranker is None:
            try:
                from rag.retrieval.search.reranker import FlashRankReranker

                self._reranker = FlashRankReranker()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "RetrievalPipeline: reranker unavailable (%s); disabling reranking",
                    exc,
                )
                self._enable_reranking = False
                return None
        return self._reranker

    def _get_sparse_encoder(self, document_id: str):
        """
        Load the BM25 encoder for *document_id* from disk (cached in memory).
        Returns None if the encoder file is not found.
        """
        if document_id in self._bm25_cache:
            return self._bm25_cache[document_id]

        pkl_path = self._output_dir / f"{document_id}_bm25.pkl"
        if not pkl_path.exists():
            logger.warning(
                "RetrievalPipeline: BM25 encoder not found at %s; "
                "sparse search will be disabled for this document",
                pkl_path,
            )
            return None

        from rag.retrieval.embeddings.sparse_encoder import BM25SparseEncoder

        enc = BM25SparseEncoder.load(pkl_path)
        self._bm25_cache[document_id] = enc
        return enc

    # ── Public API ────────────────────────────────────────────────────────────

    def index(
        self,
        hierarchy_json_path: Path,
        output_dir: Optional[Path] = None,
        pdf_path: Optional[Path] = None,
        force_reindex: bool = False,
    ):
        """
        Index a document into Qdrant.

        Delegates to :class:`~rag.retrieval.indexing.Indexer`.  Returns an
        :class:`~rag.retrieval.indexing.IndexingResult`.
        """
        return self._get_indexer().index_document(
            hierarchy_json_path=Path(hierarchy_json_path),
            output_dir=output_dir,
            pdf_path=pdf_path,
            force_reindex=force_reindex,
        )

    def query(
        self,
        query: str,
        document_id: Optional[str] = None,
        section_title_contains: Optional[str] = None,
        section_path_any: Optional[list[str]] = None,
        chunk_level: Optional[str] = None,
        section_id: Optional[str] = None,
        top_k: int = RETRIEVER_TOP_K,
        top_n: int = RERANKER_TOP_N,
        rerank: bool = True,
        exclude_reference_sections: bool = True,
    ) -> list:
        """
        Run hybrid retrieval + reranking.

        Parameters
        ----------
        query : str
            Search query (raw or LLM-expanded).
        document_id : str, optional
            Restrict search to one document.
        section_title_contains : str, optional
            Only return chunks whose section title contains this substring.
        section_path_any : list[str], optional
            Only return chunks whose ``section_path`` contains one of these
            values.
        chunk_level : str, optional
            Restrict to a chunk granularity level (``"fine"`` / ``"coarse"``).
        section_id : str, optional
            When set, results are filtered to this section only.
        top_k : int
            Candidates to retrieve before reranking.
        top_n : int
            Final results to return after reranking.
        rerank : bool
            Apply cross-encoder reranking when available.
        exclude_reference_sections : bool
            Exclude Reference/Bibliography sections from retrieval candidates.

        Returns
        -------
        list[RetrievalResult]
            Sorted by rerank score (or retrieval score when reranking is off).
        """
        from rag.retrieval.search.hybrid_retriever import HybridRetriever

        # Resolve sparse encoder (per-document BM25)
        sparse_enc = None
        if document_id:
            sparse_enc = self._get_sparse_encoder(document_id)

        if sparse_enc is None:
            # No BM25 available → fall back to dense-only via a dummy sparse encoder
            logger.info(
                "RetrievalPipeline: no BM25 encoder for document_id=%s; "
                "using dense-only retrieval",
                document_id,
            )
            sparse_enc = _DenseFallbackSparseEncoder()

        retriever = HybridRetriever(
            store_manager=self._get_store_manager(),
            dense_encoder=self._get_dense_encoder(),
            sparse_encoder=sparse_enc,
            top_k=top_k,
        )

        results = retriever.retrieve(
            query=query,
            document_id=document_id,
            section_title_contains=section_title_contains,
            section_path_any=section_path_any,
            chunk_level=chunk_level,
            section_id=section_id,
            exclude_reference_sections=exclude_reference_sections,
        )

        if not results:
            return []

        if rerank:
            results = self.rerank_results(query=query, results=results, top_n=top_n)
        else:
            results = results[:top_k]

        return results

    def rerank_results(self, query: str, results: list, top_n: int = RERANKER_TOP_N) -> list:
        """Rerank an existing result list and keep only ``top_n`` entries."""
        if not results:
            return []

        reranker = self._get_reranker()
        if reranker is None:
            return results[:top_n]

        reranked = reranker.rerank(query=query, results=results)
        return reranked[:top_n]

    def retrieve_with_section_scope(
        self,
        query: str,
        section_id: str,
        document_id: str,
        top_k: int = RETRIEVER_TOP_K,
        top_n: int = RERANKER_TOP_N,
        rerank: bool = True,
        exclude_reference_sections: bool = True,
    ) -> list:
        """
        Retrieve chunks scoped to a specific section and its descendants.

        This function enables section-aware retrieval by filtering results to only
        include chunks whose section hierarchy includes the specified section_id.
        When a parent section is queried, all descendant sections are automatically
        included in the results.

        Parameters
        ----------
        query : str
            Search query (raw or LLM-expanded).
        section_id : str
            Section ID to scope results to. The filter will match any chunk whose
            ``section_path_ids`` contains this section_id, enabling parent-to-
            descendant filtering.
        document_id : str
            Restrict search to this specific document. Required for sparse BM25
            encoding lookup.
        top_k : int, optional
            Candidates to retrieve before reranking (default: RETRIEVER_TOP_K).
        top_n : int, optional
            Final results to return after reranking (default: RERANKER_TOP_N).
        rerank : bool, optional
            Apply cross-encoder reranking when available (default: True).
        exclude_reference_sections : bool, optional
            Exclude Reference/Bibliography sections from retrieval candidates.

        Returns
        -------
        list[RetrievalResult]
            Chunks within the specified section scope, sorted by rerank score
            (or retrieval score when reranking is off). Returns empty list if
            no matching chunks found.

        Example
        -------
        ::

            pipeline = RetrievalPipeline()
            results = pipeline.retrieve_with_section_scope(
                query="What is multi-head attention?",
                section_id="3.2",
                document_id="paper-uuid",
                top_k=20,
                top_n=5,
            )
            # Returns chunks from section 3.2 and any subsections (3.2.1, 3.2.2, etc.)

        Notes
        -----
        - The section_id is checked against the ``section_path_ids`` field in each
          chunk, which contains the full ancestry of section IDs from root to leaf.
        - Parent sections automatically include all descendants; leaf sections include
          only themselves and their nested content.
        - Requires section hierarchy to be present in the indexed document.
        """
        from rag.retrieval.search.hybrid_retriever import HybridRetriever

        # Resolve sparse encoder (per-document BM25)
        sparse_enc = self._get_sparse_encoder(document_id)
        if sparse_enc is None:
            logger.info(
                "RetrievalPipeline.retrieve_with_section_scope: "
                "no BM25 encoder for document_id=%s; using dense-only retrieval",
                document_id,
            )
            sparse_enc = _DenseFallbackSparseEncoder()

        retriever = HybridRetriever(
            store_manager=self._get_store_manager(),
            dense_encoder=self._get_dense_encoder(),
            sparse_encoder=sparse_enc,
            top_k=top_k,
        )

        # Retrieve with section_path_ids filtering: only include chunks whose
        # section_path_ids contains the target section_id (number-based like "3.2")
        results = retriever.retrieve(
            query=query,
            document_id=document_id,
            section_path_ids_any=[section_id],  # Filter by ID-based ancestry
            exclude_reference_sections=exclude_reference_sections,
        )

        if not results:
            return []

        if rerank:
            results = self.rerank_results(query=query, results=results, top_n=top_n)
        else:
            results = results[:top_k]

        return results

    def collection_info(self) -> dict:
        """Return Qdrant collection metadata (points count, status)."""
        return self._get_store_manager().get_collection_info()


# ── Fallback sparse encoder (dense-only mode) ─────────────────────────────────

class _DenseFallbackSparseEncoder:
    """
    No-op sparse encoder used when BM25 is unavailable.
    Returns empty sparse vectors so the Qdrant HYBRID mode degrades
    gracefully to dense-only retrieval.
    """

    def embed_documents(self, texts):
        from qdrant_client.models import SparseVector  # type: ignore

        return [SparseVector(indices=[], values=[]) for _ in texts]

    def embed_query(self, text: str):
        from qdrant_client.models import SparseVector  # type: ignore

        return SparseVector(indices=[], values=[])
