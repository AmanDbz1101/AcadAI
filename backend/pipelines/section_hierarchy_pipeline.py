"""
Section Hierarchy Detection Pipeline.

Orchestrates the complete section hierarchy detection workflow,
building structured section trees from processed documents.
"""

import time
import logging
from pathlib import Path
from typing import Optional

from backend.models.document import ValidatedDocument
from backend.models.metadata import ProcessedDocument
from backend.models.section_hierarchy import SectionHierarchy, SectionDetectionResult
from backend.app.processing.section_detector import SectionDetector


logger = logging.getLogger(__name__)


class SectionHierarchyPipeline:
    """
    Orchestrates section hierarchy detection from validated or processed documents.
    
    Builds a hierarchical section tree that serves as the backbone for:
    - Section-aware chunking
    - Targeted retrieval
    - Reading guide generation
    """
    
    def __init__(
        self,
        min_heading_font_size: float = 10.0,
        use_docling_structure: bool = True
    ):
        """
        Initialize section hierarchy detection pipeline.
        
        Args:
            min_heading_font_size: Minimum font size to consider as heading
            use_docling_structure: Whether to prefer Docling-extracted structure
        """
        self.detector = SectionDetector(
            min_heading_font_size=min_heading_font_size,
            use_docling_structure=use_docling_structure
        )
    
    def process_from_processed_document(
        self,
        processed_doc: ProcessedDocument,
        validated_doc: Optional[ValidatedDocument] = None
    ) -> SectionDetectionResult:
        """
        Process a ProcessedDocument to detect section hierarchy.
        
        This is the preferred method when metadata has already been extracted.
        
        Args:
            processed_doc: ProcessedDocument with extracted metadata
            validated_doc: Optional ValidatedDocument for additional context
            
        Returns:
            SectionDetectionResult with detected hierarchy
        """
        logger.info(f"Starting section hierarchy detection for document {processed_doc.document_id}")
        
        start_time = time.time()
        warnings = []
        
        try:
            # Detect hierarchy
            hierarchy = self.detector.detect_from_processed_document(
                processed_doc,
                validated_doc
            )
            
            # Validate results
            if hierarchy.total_sections == 0:
                warnings.append("No sections detected in document")
            elif hierarchy.total_sections < 3:
                warnings.append(f"Only {hierarchy.total_sections} sections detected, which is unusually low")
            
            if hierarchy.confidence_score < 0.5:
                warnings.append(f"Low confidence score: {hierarchy.confidence_score:.2f}")
            
            processing_time = time.time() - start_time
            
            logger.info(
                f"Section hierarchy detection completed in {processing_time:.2f}s. "
                f"Detected {hierarchy.total_sections} sections with confidence {hierarchy.confidence_score:.2f}"
            )
            
            return SectionDetectionResult(
                hierarchy=hierarchy,
                processing_time_seconds=processing_time,
                warnings=warnings
            )
            
        except Exception as e:
            logger.error(f"Error during section hierarchy detection: {e}", exc_info=True)
            raise
    
    def process_from_validated_document(
        self,
        validated_doc: ValidatedDocument
    ) -> SectionDetectionResult:
        """
        Process a ValidatedDocument to detect section hierarchy.
        
        Use this when metadata extraction has not been performed yet.
        
        Args:
            validated_doc: ValidatedDocument from ingestion pipeline
            
        Returns:
            SectionDetectionResult with detected hierarchy
        """
        logger.info(f"Starting section hierarchy detection from raw document {validated_doc.document_id}")
        
        start_time = time.time()
        warnings = []
        
        try:
            # Detect hierarchy from raw document
            hierarchy = self.detector.detect_from_validated_document(validated_doc)
            
            # Validate results
            if hierarchy.total_sections == 0:
                warnings.append("No sections detected in document")
            elif hierarchy.total_sections < 3:
                warnings.append(f"Only {hierarchy.total_sections} sections detected, which is unusually low")
            
            if hierarchy.confidence_score < 0.5:
                warnings.append(f"Low confidence score: {hierarchy.confidence_score:.2f}")
            
            processing_time = time.time() - start_time
            
            logger.info(
                f"Section hierarchy detection completed in {processing_time:.2f}s. "
                f"Detected {hierarchy.total_sections} sections"
            )
            
            return SectionDetectionResult(
                hierarchy=hierarchy,
                processing_time_seconds=processing_time,
                warnings=warnings
            )
            
        except Exception as e:
            logger.error(f"Error during section hierarchy detection: {e}", exc_info=True)
            raise
    
    def save_hierarchy(
        self,
        hierarchy: SectionHierarchy,
        output_path: Path
    ) -> None:
        """
        Save section hierarchy to JSON file.
        
        Args:
            hierarchy: SectionHierarchy to save
            output_path: Path to output JSON file
        """
        import json
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(hierarchy.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved section hierarchy to {output_path}")
    
    def load_hierarchy(
        self,
        input_path: Path
    ) -> SectionHierarchy:
        """
        Load section hierarchy from JSON file.
        
        Args:
            input_path: Path to input JSON file
            
        Returns:
            Loaded SectionHierarchy
        """
        import json
        
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        hierarchy = SectionHierarchy.from_dict(data)
        
        logger.info(f"Loaded section hierarchy from {input_path}")
        
        return hierarchy
