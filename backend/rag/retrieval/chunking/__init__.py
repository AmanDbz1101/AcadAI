"""Chunking sub-package for section-aware document splitting."""

from rag.retrieval.chunking.models import Chunk
from rag.retrieval.chunking.section_chunker import SectionChunker

__all__ = ["Chunk", "SectionChunker"]
