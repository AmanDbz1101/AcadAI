"""
Research Paper Assistant Backend - Version 3.0

A modular backend for processing research papers with:
- Extraction Module: PDF ingestion, text extraction, metadata, section hierarchy
- RAG Module: Chunking, embeddings, vectorstore, retrieval
- Shared utilities and configuration

The backend is organized into focused modules for parallel development.
"""

__version__ = "3.0.0"
__author__ = "Research Paper Assistant Team"

# Main API app
from backend.api.app import app

# Extraction module exports
from backend.extraction.services.extraction_service import ExtractionService
from backend.extraction.models.document import ValidatedDocument
from backend.extraction.models.metadata import ProcessedDocument

# RAG module exports
from backend.rag.services.rag_service import RAGService
from backend.rag.models.chunking import ChunkedDocument

# Shared config
from backend.shared.config.settings import Settings

__all__ = [
    "app",
    "ExtractionService",
    "RAGService",
    "ValidatedDocument",
    "ProcessedDocument",
    "ChunkedDocument",
    "Settings",
]

