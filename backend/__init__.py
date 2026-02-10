"""
Research Paper Assistant Backend - Version 2.0

A production-grade backend for processing research papers with:
- PDF ingestion and validation
- Text extraction with layout preservation
- Adaptive OCR for scanned documents
- Document processing and chunking
- Hybrid retrieval (dense + sparse)
- Guide-driven question answering
"""

__version__ = "2.0.0"
__author__ = "Research Paper Assistant Team"

from backend.api.app import app
from backend.models.document import ValidatedDocument
from backend.pipelines.ingest_pipeline import IngestPipeline
from backend.services.ingestion_service import IngestionService

__all__ = [
    "app",
    "ValidatedDocument",
    "IngestPipeline",
    "IngestionService",
]
