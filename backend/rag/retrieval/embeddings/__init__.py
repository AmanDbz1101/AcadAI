"""Embeddings sub-package — dense (BGE) and sparse (BM25) encoders."""

from rag.retrieval.embeddings.dense_encoder import DenseEncoder
from rag.retrieval.embeddings.sparse_encoder import BM25SparseEncoder

__all__ = ["DenseEncoder", "BM25SparseEncoder"]
