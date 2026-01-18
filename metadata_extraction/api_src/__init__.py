"""
Metadata Extraction Module for Research Papers.

This module extracts structured metadata from research papers stored in Qdrant.
It uses deterministic heuristics for section detection and LLM for inference.

Main API:
    extract_metadata(document_id) -> PaperMetadata
    list_available_documents() -> List[str]
"""

from .extractor import extract_metadata, list_available_documents
from .models import (
    PaperMetadata,
    SectionMetadata,
    GlobalStats,
    PaperInference
)

__all__ = [
    "extract_metadata",
    "list_available_documents",
    "PaperMetadata",
    "SectionMetadata",
    "GlobalStats",
    "PaperInference"
]

__version__ = "1.0.0"
