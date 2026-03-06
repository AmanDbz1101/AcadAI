"""
Research Paper Assistant Backend - Unified LangGraph Version

A unified backend for processing research papers with:
- Extraction Module: PDF → Metadata + Hierarchy + Full Text
- RAG Module: Unified LangGraph workflow with extraction, categorization, Q&A, and summarization

Follows the Chat2Code pattern: simple, elegant, clean.
"""

__version__ = "5.0.0"
__author__ = "Research Paper Assistant Team"

# Import extraction components (no circular dependency)
from backend.extraction.extraction import PDFExtractor
from backend.extraction.models.document import ValidatedDocument
from backend.extraction.models.metadata import ProcessedDocument
from backend.extraction.models.section_hierarchy import SectionHierarchy

# Lazy import for PaperAnalysisPipeline to avoid circular imports
def get_pipeline():
    """Lazy import of PaperAnalysisPipeline to avoid circular dependencies."""
    from backend.run import PaperAnalysisPipeline
    return PaperAnalysisPipeline

__all__ = [
    "PDFExtractor",
    "ValidatedDocument",
    "ProcessedDocument",
    "SectionHierarchy",
    "get_pipeline",
]

