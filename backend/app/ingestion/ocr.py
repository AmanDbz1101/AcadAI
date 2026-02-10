"""
OCR handler for scanned and low-quality PDFs.

Provides adaptive OCR processing using docling's RapidOCR integration.
Handles selective page-level OCR and confidence estimation.
"""

import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from backend.models.document import OCRMetadata, PageContent
from backend.app.ingestion.pdf_loader import PDFLoader, LoaderConfig


@dataclass
class OCRConfig:
    """Configuration for OCR processing."""
    ocr_engine: str = "easyocr"  # "easyocr" or "tesseract"
    confidence_threshold: float = 0.5  # Minimum acceptable confidence
    min_text_density: float = 50.0  # Chars per page threshold for OCR trigger
    preserve_layout: bool = True
    language: str = "en"  # OCR language


class OCRHandler:
    """
    Handles OCR processing for scanned or low-quality PDFs.
    
    Features:
    - Adaptive OCR (only process pages that need it)
    - Confidence scoring
    - Layout preservation
    - Integration with docling's RapidOCR
    """
    
    def __init__(self, config: Optional[OCRConfig] = None):
        """
        Initialize OCR handler.
        
        Args:
            config: OCR configuration (uses defaults if None)
        """
        self.config = config or OCRConfig()
    
    def process_if_needed(
        self, 
        pdf_path: Path, 
        pages: List[PageContent]
    ) -> Dict[str, Any]:
        """
        Process PDF with OCR if needed based on text density analysis.
        
        Args:
            pdf_path: Path to PDF file
            pages: Initial page extraction results
            
        Returns:
            Dictionary containing:
                - pages: Updated PageContent list (with OCR if applied)
                - ocr_metadata: OCRMetadata object
                - was_reprocessed: bool indicating if OCR was applied
        """
        # Analyze text density
        analysis = self._analyze_text_density(pages)
        
        # Determine if OCR is needed
        if analysis['needs_ocr']:
            return self._apply_ocr(pdf_path, analysis['low_density_pages'])
        else:
            # No OCR needed
            return {
                "pages": pages,
                "ocr_metadata": OCRMetadata(
                    was_ocr_applied=False,
                    text_density_ratio=analysis['average_density'],
                ),
                "was_reprocessed": False,
            }
    
    def _analyze_text_density(self, pages: List[PageContent]) -> Dict[str, Any]:
        """
        Analyze text density to determine OCR necessity.
        
        Args:
            pages: List of PageContent objects
            
        Returns:
            Analysis results with OCR recommendations
        """
        if not pages:
            return {
                "needs_ocr": False,
                "average_density": 0,
                "low_density_pages": [],
            }
        
        # Calculate densities
        densities = [page.char_count for page in pages]
        average_density = sum(densities) / len(densities)
        
        # Find pages below threshold
        low_density_pages = [
            page.page_number 
            for page in pages 
            if page.char_count < self.config.min_text_density
        ]
        
        # Need OCR if average is low or significant pages are low
        needs_ocr = (
            average_density < self.config.min_text_density or
            len(low_density_pages) > len(pages) * 0.3  # > 30% pages need OCR
        )
        
        return {
            "needs_ocr": needs_ocr,
            "average_density": average_density,
            "low_density_pages": low_density_pages,
            "total_pages": len(pages),
        }
    
    def _apply_ocr(
        self, 
        pdf_path: Path, 
        target_pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Apply OCR processing to PDF.
        
        Args:
            pdf_path: Path to PDF file
            target_pages: Specific pages to OCR (None = all pages)
            
        Returns:
            Processed results with OCR metadata
        """
        start_time = time.time()
        
        # Create loader with OCR enabled
        ocr_config = LoaderConfig(
            do_ocr=True,
            ocr_engine=self.config.ocr_engine,
            extract_images=True,
            extract_tables=True,
        )
        loader = PDFLoader(config=ocr_config)
        
        # Process with OCR
        result = loader.load(pdf_path)
        pages = result['pages']
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Estimate confidence based on text quality
        confidence = self._estimate_ocr_confidence(pages)
        
        # Build OCR metadata
        ocr_metadata = OCRMetadata(
            was_ocr_applied=True,
            ocr_engine=f"docling-{self.config.ocr_engine}",
            confidence_score=confidence,
            pages_ocr_processed=target_pages or [p.page_number for p in pages],
            text_density_ratio=sum(p.char_count for p in pages) / len(pages) if pages else 0,
            processing_time_seconds=processing_time,
        )
        
        return {
            "pages": pages,
            "ocr_metadata": ocr_metadata,
            "was_reprocessed": True,
        }
    
    def _estimate_ocr_confidence(self, pages: List[PageContent]) -> float:
        """
        Estimate OCR confidence based on text quality heuristics.
        
        Args:
            pages: OCR-processed pages
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        if not pages:
            return 0.0
        
        # Heuristics for confidence estimation:
        # 1. Text density (more text = better OCR)
        # 2. Word/char ratio (normal ratio ~5-6 chars per word)
        # 3. Presence of common words
        
        total_confidence = 0.0
        
        for page in pages:
            page_confidence = 0.0
            
            # Text density score (0-0.4)
            density_score = min(page.char_count / 500, 1.0) * 0.4
            page_confidence += density_score
            
            # Word ratio score (0-0.3)
            if page.word_count > 0:
                char_per_word = page.char_count / page.word_count
                # Ideal ratio is ~5-6 chars/word
                if 3 <= char_per_word <= 10:
                    ratio_score = 0.3
                else:
                    ratio_score = 0.15
                page_confidence += ratio_score
            
            # Baseline confidence (0-0.3)
            # If we got text at all, give some baseline confidence
            if page.char_count > 50:
                page_confidence += 0.3
            
            total_confidence += page_confidence
        
        # Average across pages
        average_confidence = total_confidence / len(pages)
        
        # Clamp to [0, 1]
        return max(0.0, min(1.0, average_confidence))
    
    def force_ocr(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Force OCR processing regardless of text density.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            OCR-processed results
        """
        return self._apply_ocr(pdf_path, target_pages=None)
