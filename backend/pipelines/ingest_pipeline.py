"""
Ingestion pipeline orchestrator.

Coordinates the complete PDF ingestion workflow:
1. Validation
2. PDF loading
3. OCR (if needed)
4. Document object creation
5. Deduplication
"""

import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID

from backend.models.document import ValidatedDocument, DocumentStatus, OCRMetadata
from backend.app.ingestion.validation import PDFValidator, ValidationResult
from backend.app.ingestion.pdf_loader import PDFLoader, LoaderConfig
from backend.app.ingestion.ocr import OCRHandler, OCRConfig


logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Base exception for ingestion errors."""
    pass


class ValidationError(IngestionError):
    """Raised when PDF validation fails."""
    pass


class ExtractionError(IngestionError):
    """Raised when PDF extraction fails."""
    pass


class IngestPipeline:
    """
    Orchestrates the complete PDF ingestion workflow.
    
    Handles:
    - File validation
    - Text extraction
    - OCR processing (adaptive)
    - Document object creation
    - Error handling and recovery
    """
    
    def __init__(
        self,
        validator: Optional[PDFValidator] = None,
        loader: Optional[PDFLoader] = None,
        ocr_handler: Optional[OCRHandler] = None,
        enable_ocr: bool = True,
    ):
        """
        Initialize ingestion pipeline.
        
        Args:
            validator: PDF validator instance
            loader: PDF loader instance
            ocr_handler: OCR handler instance
            enable_ocr: Whether to enable adaptive OCR
        """
        self.validator = validator or PDFValidator()
        self.loader = loader or PDFLoader()
        self.ocr_handler = ocr_handler or OCRHandler()
        self.enable_ocr = enable_ocr
        
        logger.info("Ingestion pipeline initialized")
    
    def process(
        self, 
        pdf_path: Path,
        force_ocr: bool = False,
    ) -> ValidatedDocument:
        """
        Process a PDF file through the complete ingestion pipeline.
        
        Args:
            pdf_path: Path to PDF file
            force_ocr: Force OCR regardless of text density
            
        Returns:
            ValidatedDocument with extracted content
            
        Raises:
            ValidationError: If validation fails
            ExtractionError: If extraction fails
        """
        start_time = time.time()
        
        logger.info(f"Starting ingestion for: {pdf_path}")
        
        # Step 1: Validate PDF
        validation_result = self._validate(pdf_path)
        
        # Step 2: Extract text and layout
        extraction_result = self._extract(pdf_path)
        
        # Step 3: Apply OCR if needed
        if self.enable_ocr or force_ocr:
            extraction_result = self._apply_ocr_if_needed(
                pdf_path, 
                extraction_result,
                force=force_ocr
            )
        
        # Step 4: Build ValidatedDocument
        document = self._build_document(
            validation_result,
            extraction_result,
            processing_time=time.time() - start_time
        )
        
        logger.info(
            f"Ingestion completed for {pdf_path.name} "
            f"(pages: {document.page_count}, "
            f"time: {document.processing_time_seconds:.2f}s)"
        )
        
        return document
    
    def _validate(self, pdf_path: Path) -> ValidationResult:
        """
        Validate PDF file.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            ValidationResult
            
        Raises:
            ValidationError: If validation fails
        """
        logger.debug(f"Validating: {pdf_path}")
        
        result = self.validator.validate(pdf_path)
        
        if not result.is_valid:
            error_messages = [
                f"{err.error_type}: {err.message}" 
                for err in result.errors
            ]
            error_summary = "; ".join(error_messages)
            logger.error(f"Validation failed: {error_summary}")
            raise ValidationError(f"PDF validation failed: {error_summary}")
        
        logger.debug(
            f"Validation passed: {result.page_count} pages, "
            f"{result.file_size_bytes / 1024:.1f}KB"
        )
        
        return result
    
    def _extract(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Extract text and layout from PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Extraction results
            
        Raises:
            ExtractionError: If extraction fails
        """
        logger.debug(f"Extracting text from: {pdf_path}")
        
        try:
            result = self.loader.load(pdf_path)
            
            logger.debug(
                f"Extraction completed: {len(result['pages'])} pages, "
                f"{result['processing_time']:.2f}s"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Extraction failed: {str(e)}", exc_info=True)
            raise ExtractionError(f"Failed to extract PDF content: {str(e)}")
    
    def _apply_ocr_if_needed(
        self, 
        pdf_path: Path, 
        extraction_result: Dict[str, Any],
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Apply OCR if text density is too low or forced.
        
        Args:
            pdf_path: Path to PDF file
            extraction_result: Initial extraction results
            force: Force OCR regardless of density
            
        Returns:
            Updated extraction results (may include OCR)
        """
        pages = extraction_result['pages']
        
        # Check readability
        readability = self.loader.detect_readability(pages)
        
        logger.debug(
            f"Readability analysis: {readability['recommendation']} "
            f"(density: {readability['average_text_density']:.1f} chars/page)"
        )
        
        # Apply OCR if needed or forced
        if force or not readability['is_machine_readable']:
            logger.info(
                f"Applying OCR: {readability['recommendation']}"
            )
            
            try:
                ocr_result = self.ocr_handler.process_if_needed(pdf_path, pages)
                
                # Merge OCR results
                extraction_result['pages'] = ocr_result['pages']
                extraction_result['ocr_metadata'] = ocr_result['ocr_metadata']
                extraction_result['full_text'] = "\n\n".join(
                    page.text for page in ocr_result['pages']
                )
                
                logger.info(
                    f"OCR completed: confidence={ocr_result['ocr_metadata'].confidence_score:.2f}"
                )
                
            except Exception as e:
                logger.warning(f"OCR failed, using original extraction: {str(e)}")
                # Continue with non-OCR extraction
                extraction_result['ocr_metadata'] = OCRMetadata(
                    was_ocr_applied=False,
                    text_density_ratio=readability['average_text_density'],
                )
        else:
            # No OCR needed
            extraction_result['ocr_metadata'] = OCRMetadata(
                was_ocr_applied=False,
                text_density_ratio=readability['average_text_density'],
            )
        
        return extraction_result
    
    def _build_document(
        self,
        validation_result: ValidationResult,
        extraction_result: Dict[str, Any],
        processing_time: float,
    ) -> ValidatedDocument:
        """
        Build ValidatedDocument from validation and extraction results.
        
        Args:
            validation_result: Validation results
            extraction_result: Extraction results
            processing_time: Total processing time in seconds
            
        Returns:
            ValidatedDocument
        """
        document = ValidatedDocument(
            pdf_path=validation_result.pdf_path,
            pdf_hash=validation_result.pdf_hash,
            pages=extraction_result['pages'],
            full_text=extraction_result['full_text'],
            page_count=validation_result.page_count,
            file_size_bytes=validation_result.file_size_bytes,
            ocr_metadata=extraction_result.get('ocr_metadata'),
            status=DocumentStatus.COMPLETED,
            processing_time_seconds=processing_time,
            metadata=extraction_result.get('metadata', {}),
        )
        
        return document
    
    def process_batch(
        self, 
        pdf_paths: list[Path],
        continue_on_error: bool = True,
    ) -> Dict[str, Any]:
        """
        Process multiple PDFs in batch.
        
        Args:
            pdf_paths: List of PDF file paths
            continue_on_error: Continue processing if one file fails
            
        Returns:
            Dictionary with:
                - successful: List of ValidatedDocument
                - failed: List of (path, error) tuples
        """
        successful = []
        failed = []
        
        for pdf_path in pdf_paths:
            try:
                document = self.process(pdf_path)
                successful.append(document)
            except Exception as e:
                logger.error(f"Failed to process {pdf_path}: {str(e)}")
                failed.append((pdf_path, str(e)))
                
                if not continue_on_error:
                    raise
        
        logger.info(
            f"Batch processing completed: {len(successful)} successful, "
            f"{len(failed)} failed"
        )
        
        return {
            "successful": successful,
            "failed": failed,
            "total": len(pdf_paths),
        }
