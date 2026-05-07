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
import re
from pathlib import Path
from typing import Optional, Any

from rag.retrieval.config import (
    OUTPUT_DIR,
    RETRIEVER_TOP_K,
    RERANKER_TOP_N,
)

logger = logging.getLogger(__name__)

try:
    from langsmith.run_helpers import traceable
except Exception:  # noqa: BLE001
    # Keep retrieval functional even when LangSmith is not installed.
    def traceable(*_args, **_kwargs):
        def _decorator(func):
            return func

        return _decorator


_TRACE_RUNNER_CACHE: dict[str, Any] = {}


def _safe_trace_stage_name(stage: str) -> str:
    """Normalize stage names for stable LangSmith node labels."""
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(stage).strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unknown"


def _trace_retrieval_stage(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Emit a stage-specific LangSmith child run with retrieval counts."""
    safe_stage = _safe_trace_stage_name(stage)
    runner = _TRACE_RUNNER_CACHE.get(safe_stage)
    if runner is None:
        @traceable(name=f"retrieval_stage:{safe_stage}", run_type="chain")
        def _runner(event_payload: dict[str, Any]) -> dict[str, Any]:
            return event_payload

        runner = _runner
        _TRACE_RUNNER_CACHE[safe_stage] = runner

    return runner({"stage": stage, **payload})


_TRACE_CHUNK_PREVIEW_COUNT = 8
_TRACE_CHUNK_TEXT_CHARS = 280


def _safe_float(value: Any) -> float | None:
    """Convert values to float when possible, otherwise return None."""
    try:
        if value is None:
            return None
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _trace_chunk_preview(result: Any, content_chars: int = _TRACE_CHUNK_TEXT_CHARS) -> dict[str, Any]:
    """Build a compact, LangSmith-friendly preview for one retrieval result."""
    metadata = getattr(result, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}

    content = str(getattr(result, "content", "") or "")
    normalized_content = " ".join(content.split())
    if len(normalized_content) > content_chars:
        normalized_content = normalized_content[:content_chars] + "..."

    score = getattr(result, "score", None)
    score_value = _safe_float(score)
    retrieval_score = _safe_float(metadata.get("retrieval_score"))
    rerank_score = _safe_float(metadata.get("rerank_score"))

    # Before reranking, score is the retrieval score.
    if retrieval_score is None:
        retrieval_score = score_value

    # After reranking, score is typically the rerank score.
    if rerank_score is None and metadata.get("rerank_score") is not None:
        rerank_score = _safe_float(metadata.get("rerank_score"))

    preview = {
        "chunk_id": metadata.get("_id") or metadata.get("chunk_id"),
        "score": score_value,
        "retrieval_score": retrieval_score,
        "rerank_score": rerank_score,
        "section_id": metadata.get("section_id"),
        "section_title": metadata.get("section_title"),
        "content_type": metadata.get("content_type"),
        "chunk_level": metadata.get("chunk_level"),
        "content_preview": normalized_content,
    }
    # Keep traces concise by dropping optional fields that are missing.
    return {key: value for key, value in preview.items() if value is not None}


def _trace_chunk_previews(
    results: list[Any],
    limit: int = _TRACE_CHUNK_PREVIEW_COUNT,
    content_chars: int = _TRACE_CHUNK_TEXT_CHARS,
) -> list[dict[str, Any]]:
    """Serialize top retrieval results for trace visibility without huge payloads."""
    return [
        _trace_chunk_preview(result, content_chars=content_chars)
        for result in results[: max(0, int(limit))]
    ]


def _chunk_trace_key(preview: dict[str, Any], fallback_index: int) -> str:
    """Create a best-effort stable key to align chunk scores across stages."""
    chunk_id = preview.get("chunk_id")
    if chunk_id:
        return f"id:{chunk_id}"

    content_preview = str(preview.get("content_preview") or "").strip()
    if content_preview:
        return f"content:{content_preview[:160]}"

    return f"fallback:{fallback_index}"


def _build_rerank_score_transitions(
    input_results: list[Any],
    output_results: list[Any],
    limit: int = _TRACE_CHUNK_PREVIEW_COUNT,
) -> list[dict[str, Any]]:
    """Build side-by-side retrieval/rerank score pairs for reranked output chunks."""
    input_previews = _trace_chunk_previews(input_results, limit=max(len(input_results), limit))
    input_lookup: dict[str, tuple[int, dict[str, Any]]] = {}
    for idx, preview in enumerate(input_previews, start=1):
        key = _chunk_trace_key(preview, idx)
        input_lookup[key] = (idx, preview)

    transitions: list[dict[str, Any]] = []
    output_previews = _trace_chunk_previews(output_results, limit=limit)
    for idx, preview in enumerate(output_previews, start=1):
        key = _chunk_trace_key(preview, idx)
        input_rank, input_preview = input_lookup.get(key, (None, {}))

        retrieval_score = _safe_float(preview.get("retrieval_score"))
        if retrieval_score is None:
            retrieval_score = _safe_float(input_preview.get("retrieval_score"))
        rerank_score = _safe_float(preview.get("rerank_score"))
        if rerank_score is None:
            rerank_score = _safe_float(preview.get("score"))

        transition = {
            "chunk_id": preview.get("chunk_id"),
            "rank_before": input_rank,
            "rank_after": idx,
            "retrieval_score": retrieval_score,
            "rerank_score": rerank_score,
            "score_delta": (
                rerank_score - retrieval_score
                if rerank_score is not None and retrieval_score is not None
                else None
            ),
            "content_preview": preview.get("content_preview"),
        }
        transitions.append({k: v for k, v in transition.items() if v is not None})

    return transitions


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

        # Cache of loaded BM25 encoders keyed by document_id.
        # A None value means "checked and missing on disk".
        self._bm25_cache: dict[str, object | None] = {}

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
            # Cache missing state to avoid repeating the same warning
            # for every retrieval call on this document.
            self._bm25_cache[document_id] = None
            return None

        from rag.retrieval.embeddings.sparse_encoder import BM25SparseEncoder

        enc = BM25SparseEncoder.load(pkl_path)
        self._bm25_cache[document_id] = enc
        return enc

    # ── Public API ────────────────────────────────────────────────────────────

    @traceable(name="retrieval_index", run_type="chain")


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

    @traceable(name="retrieval_query", run_type="chain")


    def query(
        self,
        query: str,
        document_id: Optional[str] = None,
        section_title_contains: Optional[str] = None,
        section_path_any: Optional[list[str]] = None,
        chunk_level: Optional[str] = None,
        section_id: Optional[str] = None,
        content_type: Optional[str] = None,
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
        content_type : str, optional
            When set, results are filtered to this payload content type
            (for example ``"figure"`` or ``"table"``).
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

        using_bm25 = sparse_enc is not None
        if sparse_enc is None:
            # No BM25 available -> fall back to dense-only via a dummy sparse encoder.
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

        candidates = retriever.retrieve(
            query=query,
            document_id=document_id,
            section_title_contains=section_title_contains,
            section_path_any=section_path_any,
            chunk_level=chunk_level,
            section_id=section_id,
            content_type=content_type,
            exclude_reference_sections=exclude_reference_sections,
        )
        candidate_count = len(candidates)

        _trace_retrieval_stage(
            "candidate_retrieval",
            {
                "query": query,
                "document_id": document_id,
                "top_k_requested": top_k,
                "candidate_count": candidate_count,
                "candidate_chunks": _trace_chunk_previews(candidates),
                "using_bm25": using_bm25,
                "filters": {
                    "section_title_contains": section_title_contains,
                    "section_path_any_count": len(section_path_any or []),
                    "chunk_level": chunk_level,
                    "section_id": section_id,
                    "content_type": content_type,
                    "exclude_reference_sections": exclude_reference_sections,
                },
            },
        )

        if not candidates:            return []

        if rerank:
            results = self.rerank_results(query=query, results=candidates, top_n=top_n)
        else:
            results = candidates[:top_k]

        returned_count = len(results)
        _trace_retrieval_stage(
            "final_output",
            {
                "query": query,
                "document_id": document_id,
                "rerank_enabled": rerank,
                "top_n_requested": top_n,
                "returned_count": returned_count,
                "cutoff_count": max(candidate_count - returned_count, 0),
                "returned_chunks": _trace_chunk_previews(results),
            },
        )

        return results

    def rerank_results(self, query: str, results: list, top_n: int = RERANKER_TOP_N) -> list:
        """Rerank an existing result list and keep only ``top_n`` entries."""
        if not results:
            return []

        reranker = self._get_reranker()
        if reranker is None:
            fallback = results[:top_n]
            _trace_retrieval_stage(
                "rerank_skipped",
                {
                    "query": query,
                    "input_count": len(results),
                    "output_count": len(fallback),
                    "cutoff_count": max(len(results) - len(fallback), 0),
                    "reason": "reranker_unavailable_or_disabled",
                    "input_chunks": _trace_chunk_previews(results),
                    "output_chunks": _trace_chunk_previews(fallback),
                },
            )
            return fallback

        reranked = reranker.rerank(query=query, results=results)
        trimmed = reranked[:top_n]
        _trace_retrieval_stage(
            "rerank",
            {
                "query": query,
                "input_count": len(results),
                "reranked_count": len(reranked),
                "output_count": len(trimmed),
                "cutoff_count": max(len(reranked) - len(trimmed), 0),
                "top_n_requested": top_n,
                "input_chunks": _trace_chunk_previews(results),
                "output_chunks": _trace_chunk_previews(trimmed),
                "score_transitions": _build_rerank_score_transitions(
                    input_results=results,
                    output_results=trimmed,
                ),
            },
        )
        return trimmed

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
        using_bm25 = sparse_enc is not None
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
        candidates = retriever.retrieve(
            query=query,
            document_id=document_id,
            section_path_ids_any=[section_id],  # Filter by ID-based ancestry
            exclude_reference_sections=exclude_reference_sections,
        )
        candidate_count = len(candidates)

        _trace_retrieval_stage(
            "section_scoped_candidate_retrieval",
            {
                "query": query,
                "document_id": document_id,
                "section_id": section_id,
                "top_k_requested": top_k,
                "candidate_count": candidate_count,
                "candidate_chunks": _trace_chunk_previews(candidates),
                "using_bm25": using_bm25,
                "exclude_reference_sections": exclude_reference_sections,
            },
        )

        if not candidates:            return []

        if rerank:
            results = self.rerank_results(query=query, results=candidates, top_n=top_n)
        else:
            results = candidates[:top_k]

        returned_count = len(results)
        _trace_retrieval_stage(
            "section_scoped_final_output",
            {
                "query": query,
                "document_id": document_id,
                "section_id": section_id,
                "rerank_enabled": rerank,
                "top_n_requested": top_n,
                "returned_count": returned_count,
                "cutoff_count": max(candidate_count - returned_count, 0),
                "returned_chunks": _trace_chunk_previews(results),
            },
        )

        return results

    def retrieve_by_content_type(
        self,
        document_id: str,
        section_id: str,
        content_type: str,
        top_k: int = 10,
    ) -> list:
        """Retrieve section-scoped chunks filtered by payload content_type."""
        return self.query(
            query=content_type,
            document_id=document_id,
            section_id=section_id,
            content_type=content_type,
            top_k=top_k,
            top_n=top_k,
            rerank=False,
        )

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


# ── Module-level singleton getter ─────────────────────────────────────────────

_pipeline_singleton: Optional[RetrievalPipeline] = None


def get_retrieval_pipeline() -> RetrievalPipeline:
    """
    Get or create the process-wide singleton RetrievalPipeline instance.

    The dense encoder model is expensive to load; this function ensures it is
    instantiated only once and reused across all calls.

    Returns
    -------
    RetrievalPipeline
        The shared pipeline singleton instance.

    Example
    -------
    ::

        from rag.retrieval.pipeline import get_retrieval_pipeline

        pipeline = get_retrieval_pipeline()
        result = pipeline.query("How does attention work?", document_id="paper-123")
    """
    global _pipeline_singleton
    if _pipeline_singleton is None:
        logger.info("RetrievalPipeline: creating NEW singleton instance")
        _pipeline_singleton = RetrievalPipeline()
    else:
        logger.info("RetrievalPipeline: returning CACHED singleton instance")
    return _pipeline_singleton
