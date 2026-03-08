"""
Hybrid Retrieval System for Research Paper Assistant
======================================================
Provides section-aware chunking, dense + sparse embedding, Qdrant Cloud
indexing, hybrid vector search, and FlashRank reranking.

Public interface
----------------
    from rag.retrieval import RetrievalPipeline

    pipeline = RetrievalPipeline()
    pipeline.index(complete_json_path, hierarchy_json_path, pdf_path)
    results = pipeline.query("What is the attention mechanism?", document_id="...")
"""

from rag.retrieval.pipeline import RetrievalPipeline
from rag.retrieval.chunking.models import Chunk
from rag.retrieval.indexing.indexer import IndexingResult

__all__ = [
    "RetrievalPipeline",
    "Chunk",
    "IndexingResult",
]
