"""
Fast Extraction Module

Dual-path document processing:
1. Docling: Fast markdown extraction for immediate guide generation
2. Unstructured API: High-quality parsing with deduplication
"""

from .pipeline import FastExtractionPipeline
from .models import (
    DocumentStatus,
    SimpleMetadata,
    SectionInfo,
    DocumentRecord
)

__all__ = [
    'FastExtractionPipeline',
    'DocumentStatus',
    'SimpleMetadata',
    'SectionInfo',
    'DocumentRecord'
]
