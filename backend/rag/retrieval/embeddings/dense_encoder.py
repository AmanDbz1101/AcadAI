"""
Dense encoder using BAAI/bge-small-en-v1.5 via sentence-transformers.

Implements the LangChain ``Embeddings`` interface so the QdrantVectorStore
can use it directly.

BGE-specific note
-----------------
BGE models expect an instruction prefix ONLY at *query time*:

    query prefix  → "Represent this sentence for searching relevant passages: "
    doc prefix    → (none)

This encoder handles the prefix automatically; callers do not need to add it.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np
from langchain_core.embeddings import Embeddings

from rag.retrieval.config import DENSE_MODEL, MODEL_CACHE_DIR

logger = logging.getLogger(__name__)

# BGE query instruction prefix (applied only during query encoding)
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class DenseEncoder(Embeddings):
    """
    Wrapper around ``sentence_transformers.SentenceTransformer`` for
    BAAI/bge-small-en-v1.5 (384-dim, cosine similarity).

    Implements the LangChain :class:`~langchain_core.embeddings.Embeddings`
    protocol (``embed_documents`` / ``embed_query``) so it can be passed
    directly to ``QdrantVectorStore``.

    Parameters
    ----------
    model_name : str
        HuggingFace model identifier (default: BAAI/bge-small-en-v1.5).
    batch_size : int
        Encoding batch size; increase on GPU, reduce on CPU-only.
    normalize : bool
        L2-normalise embeddings (required for cosine via dot-product).
    device : str, optional
        ``"cuda"``, ``"cpu"``, or ``None`` (auto-detect).
    """

    def __init__(
        self,
        model_name: str = DENSE_MODEL,
        batch_size: int = 32,
        normalize: bool = True,
        device: Optional[str] = None,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.normalize = normalize
        self._model = None  # lazy load
        self._device = device

    # ── Lazy model loading ────────────────────────────────────────────────────

    def _load(self):
        if self._model is not None:
            return self._model
        from sentence_transformers import SentenceTransformer  # type: ignore

        logger.info("DenseEncoder: loading model %s …", self.model_name)
        t0 = time.time()
        cache_dir = MODEL_CACHE_DIR / "sentence_transformers"
        cache_dir.mkdir(parents=True, exist_ok=True)
        kwargs: dict = {"cache_folder": str(cache_dir)}
        if self._device is not None:
            kwargs["device"] = self._device
        self._model = SentenceTransformer(self.model_name, **kwargs)
        logger.info("DenseEncoder: model loaded in %.1fs", time.time() - t0)
        return self._model

    # ── LangChain Embeddings interface ────────────────────────────────────────

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Encode a list of document texts (no query prefix).

        Returns a list of 384-dim float vectors.
        """
        model = self._load()
        vectors = model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        """
        Encode a query string with the BGE instruction prefix.

        Returns a single 384-dim float vector.
        """
        model = self._load()
        prefixed = _BGE_QUERY_PREFIX + text
        vector = model.encode(
            prefixed,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )
        return vector.tolist()

    # ── Convenience np wrappers ───────────────────────────────────────────────

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        """Return document embeddings as a (N, D) float32 np array."""
        return np.array(self.embed_documents(texts), dtype=np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        """Return query embedding as a (D,) float32 np array."""
        return np.array(self.embed_query(text), dtype=np.float32)

    @property
    def embedding_dimension(self) -> int:
        """Output dimensionality (loaded lazily)."""
        model = self._load()
        return model.get_sentence_embedding_dimension()
