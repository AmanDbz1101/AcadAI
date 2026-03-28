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
import re
from typing import Optional

from rag.retrieval.config import RETRIEVER_TOP_K, RRF_K, SPARSE_VECTOR_NAME, DENSE_VECTOR_NAME

logger = logging.getLogger(__name__)

_REFERENCE_SECTION_HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*)?\s*[:.)-]?\s*(?:references?|bibliography|works cited)\b",
    flags=re.IGNORECASE,
)


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
        rrf_k: int | None = RRF_K,
    ) -> None:
        self.store_manager = store_manager
        self.dense_encoder = dense_encoder
        self.sparse_encoder = sparse_encoder
        self.top_k = top_k
        self.rrf_k = rrf_k
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
        section_id: Optional[str] = None,
        section_path_ids_any: Optional[list[str]] = None,
        content_type: Optional[str] = None,
        exclude_reference_sections: bool = True,
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
            the provided titles (legacy title-based filtering).
        chunk_level : str, optional
            Restrict retrieval to one chunk granularity (``"fine"`` or
            ``"coarse"``).
        section_id : str, optional
            When set, results are filtered to this section only.
        section_path_ids_any : list[str], optional
            Restrict to chunks whose ``section_path_ids`` array contains any of
            the provided section IDs (numbering-based, e.g., "3.2.1"). Enables
            parent-to-descendant filtering (parent "3" matches children "3.2", "3.2.1").
        exclude_reference_sections : bool, optional
            When True (default), chunks from Reference/Bibliography sections are
            excluded from retrieval results.

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
            section_id,
            section_path_ids_any,
            content_type,
            exclude_reference_sections,
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

        if exclude_reference_sections:
            filtered = [
                result
                for result in results
                if not self._metadata_is_reference_section(result.metadata)
            ]
            removed = len(results) - len(filtered)
            if removed:
                logger.info(
                    "HybridRetriever: removed %d reference-section results for query='%s'",
                    removed,
                    query[:60],
                )
            results = filtered

        return results

    # ── Low-level search helpers ──────────────────────────────────────────────

    def _hybrid_search(self, query: str, payload_filter):
        vs = self._get_vector_store()
        fusion_query = self._build_hybrid_fusion_query()

        # Newer LangChain/Qdrant builds accept explicit fusion query. Older
        # versions ignore this argument, so we retry without it on TypeError.
        try:
            return vs.similarity_search_with_score(
                query,
                k=self.top_k,
                filter=payload_filter,
                hybrid_fusion=fusion_query,
            )
        except TypeError:
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

    def _build_hybrid_fusion_query(self):
        """Build a Qdrant fusion query while staying compatible across versions."""
        from qdrant_client import models  # type: ignore

        if self.rrf_k is not None:
            try:
                return models.FusionQuery(fusion=models.Rrf(k=int(self.rrf_k)))
            except Exception:  # noqa: BLE001
                logger.debug(
                    "HybridRetriever: rrf_k=%s not supported by FusionQuery in this qdrant-client; using default RRF",
                    self.rrf_k,
                )

        return models.FusionQuery(fusion=models.Fusion.RRF)

    # ── Filter builder ────────────────────────────────────────────────────────

    @staticmethod
    def _build_filter(
        document_id: Optional[str],
        section_title_contains: Optional[str],
        section_path_any: Optional[list[str]],
        chunk_level: Optional[str],
        section_id: Optional[str] = None,
        section_path_ids_any: Optional[list[str]] = None,
        content_type: Optional[str] = None,
        exclude_reference_sections: bool = True,
    ):
        """Build a ``qdrant_client.models.Filter`` or return None."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchText  # type: ignore

        try:
            from qdrant_client.models import MatchAny  # type: ignore
        except Exception:  # noqa: BLE001
            MatchAny = None

        conditions = []
        must_not_conditions = []

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

        # New: ID-based section filtering (numbering-based like "3.2.1")
        if section_path_ids_any:
            if MatchAny is not None:
                conditions.append(
                    FieldCondition(
                        key="section_path_ids",
                        match=MatchAny(any=section_path_ids_any),
                    )
                )
            else:
                # Older qdrant-client fallback (best-effort single value).
                conditions.append(
                    FieldCondition(
                        key="section_path_ids",
                        match=MatchValue(value=section_path_ids_any[0]),
                    )
                )

        if chunk_level:
            conditions.append(
                FieldCondition(
                    key="chunk_level",
                    match=MatchValue(value=chunk_level),
                )
            )

        if section_id:
            conditions.append(
                FieldCondition(
                    key="section_id",
                    match=MatchValue(value=section_id),
                )
            )

        if content_type:
            conditions.append(
                FieldCondition(
                    key="content_type",
                    match=MatchValue(value=content_type),
                )
            )

        if exclude_reference_sections:
            reference_terms = ["reference", "bibliography", "works cited"]
            for term in reference_terms:
                must_not_conditions.append(
                    FieldCondition(
                        key="section_title",
                        match=MatchText(text=term),
                    )
                )

        if not conditions and not must_not_conditions:
            return None

        return Filter(
            must=conditions or None,
            must_not=must_not_conditions or None,
        )

    @staticmethod
    def _is_reference_heading(value: object) -> bool:
        if not isinstance(value, str):
            return False
        heading = " ".join(value.split())
        if not heading:
            return False
        return bool(_REFERENCE_SECTION_HEADING_RE.match(heading))

    @classmethod
    def _metadata_is_reference_section(cls, metadata: dict | None) -> bool:
        if not isinstance(metadata, dict):
            return False

        if cls._is_reference_heading(metadata.get("section_title")):
            return True

        section_path = metadata.get("section_path")
        if isinstance(section_path, list):
            for item in section_path:
                if cls._is_reference_heading(item):
                    return True
        elif cls._is_reference_heading(section_path):
            return True

        return False
