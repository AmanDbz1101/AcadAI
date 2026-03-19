"""
Qdrant collection manager.

Handles creation and lifecycle of a Qdrant collection configured for
*hybrid retrieval*: a named dense vector (cosine) and a named sparse vector
(inner-product / dot).  Uses the Qdrant Cloud REST API via ``qdrant_client``.
"""

from __future__ import annotations

import logging
from typing import Optional

from rag.retrieval.config import (
    QDRANT_URL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION_NAME,
    DENSE_VECTOR_SIZE,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
)

logger = logging.getLogger(__name__)


class QdrantStoreManager:
    """
    Manages the lifecycle of a Qdrant collection for hybrid retrieval.

    Parameters
    ----------
    url : str, optional
        Qdrant endpoint URL. Defaults to ``QDRANT_URL`` from config.
    api_key : str, optional
        Qdrant API key.  Defaults to ``QDRANT_API_KEY`` from config.
    collection_name : str, optional
        Collection name.  Defaults to ``QDRANT_COLLECTION_NAME`` from config.
    dense_vector_size : int
        Dimension of the dense embeddings vector (default 384 for BGE-small).
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection_name: Optional[str] = None,
        dense_vector_size: int = DENSE_VECTOR_SIZE,
    ) -> None:
        self.url = url or QDRANT_URL
        self.api_key = api_key or QDRANT_API_KEY
        self.collection_name = collection_name or QDRANT_COLLECTION_NAME
        self.dense_vector_size = dense_vector_size
        self._client = None  # lazy

    # ── Client ────────────────────────────────────────────────────────────────

    @property
    def client(self):
        """Lazily-initialised ``QdrantClient``."""
        if self._client is not None:
            return self._client
        from qdrant_client import QdrantClient  # type: ignore

        if self.url and self.api_key:
            self._client = QdrantClient(url=self.url, api_key=self.api_key)
            logger.info("QdrantStoreManager: connected to cloud at %s", self.url)
        elif self.url:
            self._client = QdrantClient(url=self.url)
            logger.info("QdrantStoreManager: connected (no API key) at %s", self.url)
        else:
            # Fall back to local in-memory for development
            self._client = QdrantClient(":memory:")
            logger.warning(
                "QdrantStoreManager: QDRANT_URL not set — using in-memory store "
                "(data will be lost on process exit)"
            )
        return self._client

    # ── Collection lifecycle ──────────────────────────────────────────────────

    def collection_exists(self) -> bool:
        """Return True if the collection already exists in Qdrant."""
        try:
            self.client.get_collection(self.collection_name)
            return True
        except Exception:  # noqa: BLE001
            return False

    def create_collection(self) -> None:
        """
        Create the hybrid collection with:
        - ``dense``  — VectorParams (size=384, distance=Cosine)
        - ``sparse`` — SparseVectorParams (on-disk index disabled for speed)

        Skips creation if the collection already exists.
        """
        from qdrant_client.models import (  # type: ignore
            Distance,
            VectorParams,
            SparseVectorParams,
            SparseIndexParams,
        )

        if self.collection_exists():
            logger.info(
                "QdrantStoreManager: collection '%s' already exists — skipping creation",
                self.collection_name,
            )
            self.ensure_indexes()
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: VectorParams(
                    size=self.dense_vector_size,
                    distance=Distance.COSINE,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: SparseVectorParams(
                    index=SparseIndexParams(on_disk=False)
                )
            },
        )
        logger.info(
            "QdrantStoreManager: created collection '%s' "
            "(dense=%d-dim cosine, sparse=%s)",
            self.collection_name,
            self.dense_vector_size,
            SPARSE_VECTOR_NAME,
        )

        self.ensure_indexes()

    def ensure_indexes(self) -> None:
        """
        Ensure the required payload indexes exist on the collection.

        - ``document_id`` — KEYWORD index for exact-match filtering.
        - ``section_title`` — TEXT (full-text) index required by ``MatchText``.
        - ``section_path`` — KEYWORD index for section-scoped ``MatchAny``.
        - ``chunk_level`` — KEYWORD index for fine/coarse filtering.

        Safe to call multiple times; silently ignores conflicts.
        """
        from qdrant_client.models import (  # type: ignore
            PayloadSchemaType,
            TextIndexParams,
            TokenizerType,
        )

        # document_id: keyword exact-match
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="document_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info("QdrantStoreManager: ensured keyword index on 'document_id'")
        except Exception as exc:  # noqa: BLE001
            logger.debug("document_id index already exists or failed: %s", exc)

        # section_title: full-text index (required for MatchText)
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="section_title",
                field_schema=TextIndexParams(
                    type="text",
                    tokenizer=TokenizerType.WORD,
                    lowercase=True,
                ),
            )
            logger.info("QdrantStoreManager: ensured text index on 'section_title'")
        except Exception as exc:  # noqa: BLE001
            logger.debug("section_title text index already exists or failed: %s", exc)

        # section_path: keyword array index (for MatchAny section scoping)
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="section_path",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info("QdrantStoreManager: ensured keyword index on 'section_path'")
        except Exception as exc:  # noqa: BLE001
            logger.debug("section_path index already exists or failed: %s", exc)

        # chunk_level: exact match on fine/coarse.
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="chunk_level",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info("QdrantStoreManager: ensured keyword index on 'chunk_level'")
        except Exception as exc:  # noqa: BLE001
            logger.debug("chunk_level index already exists or failed: %s", exc)

    def delete_collection(self) -> None:
        """Delete the collection if it exists."""
        if self.collection_exists():
            self.client.delete_collection(self.collection_name)
            logger.info(
                "QdrantStoreManager: deleted collection '%s'", self.collection_name
            )

    def get_collection_info(self) -> dict:
        """Return a summary dict of the collection (points count, status, etc.)."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "status": str(info.status),
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # ── LangChain VectorStore accessor ────────────────────────────────────────

    def get_vector_store(self, dense_encoder, sparse_encoder) -> "QdrantVectorStore":
        """
        Construct and return a ``langchain_qdrant.QdrantVectorStore`` configured
        for hybrid retrieval.

        Parameters
        ----------
        dense_encoder : DenseEncoder
            LangChain Embeddings-compatible dense encoder.
        sparse_encoder : BM25SparseEncoder
            SparseEmbeddings-compatible sparse encoder.

        Returns
        -------
        QdrantVectorStore
            Ready for ``similarity_search`` in HYBRID mode.
        """
        from langchain_qdrant import QdrantVectorStore, RetrievalMode  # type: ignore

        return QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=dense_encoder,
            sparse_embedding=sparse_encoder,
            retrieval_mode=RetrievalMode.HYBRID,
            vector_name=DENSE_VECTOR_NAME,
            sparse_vector_name=SPARSE_VECTOR_NAME,
            content_payload_key="content",   # our chunks use "content", not "page_content"
        )

    def delete_document_points(self, document_id: str) -> int:
        """
        Delete all points that belong to *document_id* from the collection.

        Returns the number of points removed (0 if none existed or collection
        does not exist).
        """
        if not self.collection_exists():
            return 0
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore

            result = self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id),
                        )
                    ]
                ),
                wait=True,
            )
            logger.info(
                "QdrantStoreManager: deleted existing points for document %s (status=%s)",
                document_id,
                result.status,
            )
            return 1  # count unavailable from delete result; non-zero signals success
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "QdrantStoreManager: could not delete points for %s: %s",
                document_id,
                exc,
            )
            return 0

    def document_is_indexed(self, document_id: str) -> bool:
        """
        Return True if at least one point for *document_id* exists in the
        collection (cheap scroll-based check).
        """
        if not self.collection_exists():
            return False
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore

            hits, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False,
            )
            return len(hits) > 0
        except Exception:  # noqa: BLE001
            return False
