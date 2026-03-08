"""
BM25 sparse encoder.

Produces Qdrant-compatible sparse vectors from BM25 term weights so that
the dot-product of a document sparse vector and a query sparse vector equals
the BM25 relevance score.

Formula
-------
Document representation::

    w(t, d) = IDF(t) * (TF(t,d) * (k1+1)) / (TF(t,d) + k1*(1-b+b*|d|/avgdl))

Query representation::

    w(t, q) = IDF(t)   for each term t in q that is in the vocabulary

dot_product(doc_vec, query_vec) ≈ BM25(d, q)

Implements the ``langchain_qdrant.sparse_embeddings.SparseEmbeddings`` protocol
so it can be passed directly to ``QdrantVectorStore``.
"""

from __future__ import annotations

import logging
import pickle
import re
import string
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Tokeniser ─────────────────────────────────────────────────────────────────

_PUNCT = re.compile(r"[" + re.escape(string.punctuation) + r"]")


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace, drop empty tokens."""
    text = text.lower()
    text = _PUNCT.sub(" ", text)
    return [t for t in text.split() if t]


# ── BM25SparseEncoder ─────────────────────────────────────────────────────────

class BM25SparseEncoder:
    """
    BM25-based sparse encoder compatible with the
    ``langchain_qdrant.sparse_embeddings.SparseEmbeddings`` protocol.

    Usage
    -----
    1. ``fit(corpus)`` on the document collection.
    2. ``embed_documents(texts)`` at indexing time.
    3. ``embed_query(text)`` at retrieval time.
    4. ``save(path)`` / ``BM25SparseEncoder.load(path)`` for persistence.

    Parameters
    ----------
    k1 : float
        BM25 term-frequency saturation parameter (default 1.5).
    b : float
        BM25 document-length normalisation parameter (default 0.75).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

        # Set after fit()
        self._vocab: dict[str, int] = {}       # token → integer index
        self._idf: dict[int, float] = {}       # index → IDF value
        self._avgdl: float = 0.0
        self._fitted: bool = False

    # ── Fitting ───────────────────────────────────────────────────────────────

    def fit(self, corpus: list[str]) -> "BM25SparseEncoder":
        """
        Fit vocabulary and IDF table from *corpus*.

        Parameters
        ----------
        corpus : list[str]
            All document texts that will be indexed.  Pass this once before
            calling :meth:`embed_documents`.

        Returns
        -------
        self
        """
        if not corpus:
            raise ValueError("corpus must be non-empty")

        # Tokenise once
        tokenized: list[list[str]] = [_tokenize(doc) for doc in corpus]

        # Build vocabulary  (only tokens that appear in at least 1 doc)
        vocab_set: set[str] = {token for doc in tokenized for token in doc}
        self._vocab = {token: idx for idx, token in enumerate(sorted(vocab_set))}

        n_docs = len(tokenized)
        total_len = 0

        # Document frequencies
        df: dict[int, int] = {}
        for tokens in tokenized:
            total_len += len(tokens)
            for token in set(tokens):
                idx = self._vocab.get(token)
                if idx is not None:
                    df[idx] = df.get(idx, 0) + 1

        self._avgdl = total_len / n_docs if n_docs > 0 else 1.0

        # IDF with BM25+ smoothing: log((N - df + 0.5) / (df + 0.5) + 1)
        import math

        self._idf = {
            idx: math.log((n_docs - freq + 0.5) / (freq + 0.5) + 1.0)
            for idx, freq in df.items()
        }

        self._fitted = True
        logger.info(
            "BM25SparseEncoder: fitted on %d docs, vocab size %d, avgdl %.1f",
            n_docs,
            len(self._vocab),
            self._avgdl,
        )
        return self

    # ── SparseEmbeddings interface ────────────────────────────────────────────

    def embed_documents(self, texts: list[str]):
        """
        Encode a batch of documents to BM25 sparse vectors.

        Returns a list of ``qdrant_client.models.SparseVector``.
        """
        return [self._encode_document(t) for t in texts]

    def embed_query(self, text: str):
        """
        Encode a query to a BM25 sparse vector (IDF weighting).

        Returns a ``qdrant_client.models.SparseVector``.
        """
        return self._encode_query(text)

    # ── Internal encoders ─────────────────────────────────────────────────────

    def _encode_document(self, text: str):
        """Compute BM25 document-side sparse vector."""
        from qdrant_client.models import SparseVector  # type: ignore

        self._assert_fitted()
        tokens = _tokenize(text)
        if not tokens:
            return SparseVector(indices=[], values=[])

        doc_len = len(tokens)

        # Term frequency dict for this document
        tf: dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1

        indices: list[int] = []
        values: list[float] = []

        for token, freq in tf.items():
            idx = self._vocab.get(token)
            if idx is None:
                continue
            idf = self._idf.get(idx, 0.0)
            if idf == 0.0:
                continue
            # BM25 normalised TF
            norm_tf = (freq * (self.k1 + 1)) / (
                freq + self.k1 * (1 - self.b + self.b * doc_len / self._avgdl)
            )
            indices.append(idx)
            values.append(idf * norm_tf)

        return SparseVector(indices=indices, values=values)

    def _encode_query(self, text: str):
        """Compute BM25 query-side sparse vector (IDF only)."""
        from qdrant_client.models import SparseVector  # type: ignore

        self._assert_fitted()
        tokens = _tokenize(text)
        if not tokens:
            return SparseVector(indices=[], values=[])

        seen: set[int] = set()
        indices: list[int] = []
        values: list[float] = []

        for token in tokens:
            idx = self._vocab.get(token)
            if idx is None or idx in seen:
                continue
            idf = self._idf.get(idx, 0.0)
            if idf > 0.0:
                indices.append(idx)
                values.append(idf)
                seen.add(idx)

        return SparseVector(indices=indices, values=values)

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Serialise vocabulary + IDF table + BM25 params to *path*."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "vocab": self._vocab,
            "idf": self._idf,
            "avgdl": self._avgdl,
            "k1": self.k1,
            "b": self.b,
            "fitted": self._fitted,
        }
        with open(path, "wb") as f:
            pickle.dump(state, f)
        logger.info("BM25SparseEncoder: saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "BM25SparseEncoder":
        """Load a previously saved encoder from *path*."""
        path = Path(path)
        with open(path, "rb") as f:
            state = pickle.load(f)
        enc = cls(k1=state["k1"], b=state["b"])
        enc._vocab = state["vocab"]
        enc._idf = state["idf"]
        enc._avgdl = state["avgdl"]
        enc._fitted = state["fitted"]
        logger.info(
            "BM25SparseEncoder: loaded from %s (vocab size %d)",
            path,
            len(enc._vocab),
        )
        return enc

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _assert_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError(
                "BM25SparseEncoder has not been fitted. Call fit(corpus) first."
            )

    @property
    def vocab_size(self) -> int:
        return len(self._vocab)

    @property
    def is_fitted(self) -> bool:
        return self._fitted
