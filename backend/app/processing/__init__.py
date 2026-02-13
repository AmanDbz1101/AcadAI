"""
Document processing module.

Handles metadata extraction, layout analysis, and content processing.
"""

from backend.app.processing.metadata_extractor_v2 import MetadataExtractor
from backend.app.processing.section_detector import SectionDetector

__all__ = [
    'MetadataExtractor',
    'SectionDetector',
]
