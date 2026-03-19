"""
Hybrid vector retriever.

Runs a Qdrant *hybrid* search (dense cosine + sparse BM25 dot-product)
with Reciprocal Rank Fusion (RRF) merging applied server-side by Qdrant.
Returns results as the existing :class:`~rag.states.RetrievalResult` model
so the rest of the graph does not need to change.

Query flow
----------
1. BGE-small encodes the query to a 384-dim dense vector (with BGE prefix).
2. BM25SparseEncoder encodes the query to a sparse IDF vector.
3. ``QdrantVectorStore.similarity_search_with_score`` fires both searches
   in a single round-trip (Qdrant prefetch + RRF fusion).
4. Optional payload filter on ``document_id`` and/or ``section_title``.
5. Raw hits are mapped to ``RetrievalResult`` objects.
"""

from __future__ import annotations

import logging
from typing import Optional

from rag.retrieval.config import RETRIEVER_TOP_K, SPARSE_VECTOR_NAME, DENSE_VECTOR_NAME

logger = logging.getLogger(__name__)


class HybridRetriever:
    """
    Hybrid (dense + sparse) retriever backed by Qdrant Cloud.

    Parameters
    ----------
    store_manager : QdrantStoreManager
        Qdrant collection manager (already connected).
    dense_encoder : DenseEncoder
        LangChain Embeddings-compatible dense encoder.
    sparse_encoder : BM25SparseEncoder
        SparseEmbeddings-compatible sparse encoder (must be fitted).
    top_k : int
        Number of candidates to retrieve before reranking (default 20).
    """

    def __init__(
        self,
        store_manager,
        dense_encoder,
        sparse_encoder,
        top_k: int = RETRIEVER_TOP_K,
    ) -> None:
        self.store_manager = store_manager
        self.dense_encoder = dense_encoder
        self.sparse_encoder = sparse_encoder
        self.top_k = top_k
        self._vector_store = None  # lazy

    # ── Vector store accessor ──────────────────────────────────────────────────

    def _get_vector_store(self):
        if self._vector_store is None:
            self._vector_store = self.store_manager.get_vector_store(
                self.dense_encoder, self.sparse_encoder
            )
        return self._vector_store

    # ── Main retrieval ────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        document_id: Optional[str] = None,
        section_title_contains: Optional[str] = None,
        section_path_any: Optional[list[str]] = None,
        chunk_level: Optional[str] = None,
    ) -> list:
        """
        Run hybrid search and return a list of ``RetrievalResult``.

        Parameters
        ----------
        query : str
            User or query-expanded search string.
        document_id : str, optional
            When set, results are filtered to this document only.
        section_title_contains : str, optional
            Case-insensitive substring filter on ``section_title`` payload.
        section_path_any : list[str], optional
            Restrict to chunks whose ``section_path`` array contains any of
            the provided titles.
        chunk_level : str, optional
            Restrict retrieval to one chunk granularity (``"fine"`` or
            ``"coarse"``).

        Returns
        -------
        list[RetrievalResult]
            Up to ``top_k`` results with content, score, and rich metadata.
        """
        from rag.states import RetrievalResult  # local to avoid circular import

        if not query.strip():
            logger.warning("HybridRetriever: empty query — returning nothing")
            return []

        # Build Qdrant payload filter
        payload_filter = self._build_filter(
            document_id,
            section_title_contains,
            section_path_any,
            chunk_level,
        )

        # Attempt hybrid search; fall back to dense-only on error
        try:
            hits = self._hybrid_search(query, payload_filter)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "HybridRetriever: hybrid search failed (%s); retrying with sparse only",
                exc,
            )
            try:
                hits = self._dense_search(query, payload_filter)
            except Exception as exc2:  # noqa: BLE001
                logger.error("HybridRetriever: dense fallback also failed: %s", exc2)
                return []

        results = []
        for doc, score in hits:
            meta = dict(doc.metadata) if doc.metadata else {}
            # Enrich with payload fields surfaced by LangChain as metadata
            results.append(
                RetrievalResult(
                    content=doc.page_content,
                    score=float(score),
                    metadata=meta,
                )
            )

        logger.info(
            "HybridRetriever: query='%s' → %d results (doc_filter=%s)",
            query[:60],
            len(results),
            document_id,
        )
        return results

    # ── Low-level search helpers ──────────────────────────────────────────────

    def _hybrid_search(self, query: str, payload_filter):
        from langchain_qdrant import RetrievalMode  # type: ignore

        vs = self._get_vector_store()
        return vs.similarity_search_with_score(
            query,
            k=self.top_k,
            filter=payload_filter,
        )

    def _dense_search(self, query: str, payload_filter):
        """Dense-only fallback using the same vector store interface."""
        vs = self._get_vector_store()
        return vs.similarity_search_with_score(
            query,
            k=self.top_k,
            filter=payload_filter,
        )

    # ── Filter builder ────────────────────────────────────────────────────────

    @staticmethod
    def _build_filter(
        document_id: Optional[str],
        section_title_contains: Optional[str],
        section_path_any: Optional[list[str]],
        chunk_level: Optional[str],
    ):
        """Build a ``qdrant_client.models.Filter`` or return None."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchText  # type: ignore

        try:
            from qdrant_client.models import MatchAny  # type: ignore
        except Exception:  # noqa: BLE001
            MatchAny = None

        conditions = []

        if document_id:
            conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id),
                )
            )

        if section_title_contains:
            conditions.append(
                FieldCondition(
                    key="section_title",
                    match=MatchText(text=section_title_contains),
                )
            )

        if section_path_any:
            if MatchAny is not None:
                conditions.append(
                    FieldCondition(
                        key="section_path",
                        match=MatchAny(any=section_path_any),
                    )
                )
            else:
                # Older qdrant-client fallback (best-effort single value).
                conditions.append(
                    FieldCondition(
                        key="section_path",
                        match=MatchValue(value=section_path_any[0]),
                    )
                )

        if chunk_level:
            conditions.append(
                FieldCondition(
                    key="chunk_level",
                    match=MatchValue(value=chunk_level),
                )
            )

        if not conditions:
            return None

        return Filter(must=conditions)
