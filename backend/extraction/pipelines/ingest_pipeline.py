"""
Ingestion pipeline orchestrator.

Coordinates the complete PDF ingestion workflow:
1. Validation
2. PDF loading
3. OCR (if needed)
4. Document object creation
5. Deduplication
"""

import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from backend.extraction.models.document import ValidatedDocument, DocumentStatus, OCRMetadata
from backend.extraction.app.validation import PDFValidator, ValidationResult
from backend.extraction.app.pdf_loader import PDFLoader, LoaderConfig
from backend.extraction.app.ocr import OCRHandler, OCRConfig


logger = logging.getLogger(__name__)

import re
from typing import Any

try:
    from langsmith.run_helpers import traceable
except Exception:  # noqa: BLE001
    def traceable(*_args, **_kwargs):
        def _decorator(func):
            return func

        return _decorator

_TRACE_RUNNER_CACHE: dict[str, Any] = {}


def _safe_trace_stage_name(stage: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(stage).strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unknown"


def _trace_ingest_stage(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    safe_stage = _safe_trace_stage_name(stage)
    runner = _TRACE_RUNNER_CACHE.get(safe_stage)
    if runner is None:
        @traceable(name=f"ingest_stage:{safe_stage}", run_type="chain")
        def _runner(event_payload: dict[str, Any]) -> dict[str, Any]:
            return event_payload

        runner = _runner
        _TRACE_RUNNER_CACHE[safe_stage] = runner

    return runner({"stage": stage, **payload})


class IngestionError(Exception):
    """Base exception for ingestion errors."""
    pass


class ValidationError(IngestionError):
    """Raised when PDF validation fails."""
    pass


class ExtractionError(IngestionError):
    """Raised when PDF extraction fails."""
    pass


class DeduplicationSkipped(IngestionError):
    """Raised when a duplicate PDF is detected and skipped."""

    def __init__(self, pdf_hash: str, existing_paper_id: Optional[int] = None):
        self.pdf_hash = pdf_hash
        self.existing_paper_id = existing_paper_id
        super().__init__(f"Duplicate PDF detected (hash={pdf_hash})")


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
        enable_incremental: bool = False,
        cache_dir: Optional[Path] = None,
        dedup_checker: Optional[Callable[[str], Optional[int]]] = None,
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
        self.enable_incremental = enable_incremental
        self.cache_dir = cache_dir
        self.dedup_checker = dedup_checker
        
        logger.info("Ingestion pipeline initialized")
    
    @traceable(name="ingest_pipeline", run_type="chain")

    
    def process(
        self, 
        pdf_path: Path,
        force_ocr: bool = False,
        skip_if_exists: bool = False,
        postgres_dsn: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        enable_incremental: Optional[bool] = None,
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
        _trace_ingest_stage("start", {"pdf_path": str(pdf_path)})
        
        # Step 1: Validate PDF
        validation_result = self._validate(pdf_path)
        _trace_ingest_stage("validated", {"pdf_path": str(pdf_path), "pdf_hash": validation_result.pdf_hash})

        # Optional deduplication by PDF hash (Postgres-backed)
        if skip_if_exists and validation_result.pdf_hash:
            existing_id = self._check_dedup(validation_result.pdf_hash, postgres_dsn)
            if existing_id is not None:
                raise DeduplicationSkipped(validation_result.pdf_hash, existing_id)

        # Optional incremental reuse of cached ingestion output
        effective_cache_dir = cache_dir or self.cache_dir
        incremental_enabled = self.enable_incremental if enable_incremental is None else enable_incremental
        if incremental_enabled and validation_result.pdf_hash and effective_cache_dir:
            cached = self._load_cached_document(validation_result.pdf_hash, effective_cache_dir)
            if cached is not None:
                cached_pdf_path = getattr(cached, "pdf_path", None)
                if cached_pdf_path and Path(cached_pdf_path).exists():
                    logger.info(
                        "IngestPipeline: valid cache hit, pdf_path exists: %s",
                        cached_pdf_path,
                    )
                    logger.info(
                        "Using cached ingestion result for %s (hash=%s)",
                        pdf_path.name,
                        validation_result.pdf_hash,
                    )
                    return cached

                logger.warning(
                    "IngestPipeline: cache hit for %s but cached pdf_path does not exist: %s "
                    "— invalidating cache and re-ingesting",
                    pdf_path.name,
                    cached_pdf_path,
                )
                try:
                    self._cache_path(validation_result.pdf_hash, effective_cache_dir).unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning("Failed to invalidate stale ingestion cache: %s", exc)
        
        # Step 2: Extract text and layout
        extraction_result = self._extract(pdf_path)
        _trace_ingest_stage("extracted", {"pdf_path": str(pdf_path), "pages": len(extraction_result.get('pages', []))})
        
        # Step 3: Apply OCR if needed
        if self.enable_ocr or force_ocr:
            extraction_result = self._apply_ocr_if_needed(
                pdf_path, 
                extraction_result,
                force=force_ocr
            )
            _trace_ingest_stage("ocr_checked", {"pdf_path": str(pdf_path), "was_reprocessed": bool(extraction_result.get('ocr_metadata') and extraction_result.get('ocr_metadata').was_ocr_applied)})
        
        # Step 4: Build ValidatedDocument
        document = self._build_document(
            validation_result,
            extraction_result,
            processing_time=time.time() - start_time
        )
        _trace_ingest_stage("document_built", {"document_id": str(document.document_id), "page_count": document.page_count})

        if incremental_enabled and validation_result.pdf_hash and effective_cache_dir:
            self._save_cached_document(document, effective_cache_dir)
        
        logger.info(
            f"Ingestion completed for {pdf_path.name} "
            f"(pages: {document.page_count}, "
            f"time: {document.processing_time_seconds:.2f}s)"
        )
        
        return document

    def _check_dedup(self, pdf_hash: str, postgres_dsn: Optional[str]) -> Optional[int]:
        if self.dedup_checker:
            return self.dedup_checker(pdf_hash)

        if not postgres_dsn:
            return None

        try:
            from backend.extraction.persistence import PostgresPaperStore

            store = PostgresPaperStore(postgres_dsn)
            return store.get_paper_id_by_hash(pdf_hash)
        except Exception as exc:
            logger.warning("Deduplication check failed: %s", exc)
            return None

    @staticmethod
    def _cache_path(pdf_hash: str, cache_dir: Path) -> Path:
        return cache_dir / f"{pdf_hash}_ingest.json"

    def _load_cached_document(self, pdf_hash: str, cache_dir: Path) -> Optional[ValidatedDocument]:
        cache_path = self._cache_path(pdf_hash, cache_dir)
        if not cache_path.exists():
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            data = payload.get("validated_document", {})
            return ValidatedDocument.model_validate(data)
        except Exception as exc:
            logger.warning("Failed to read ingestion cache %s: %s", cache_path, exc)
            return None

    def _save_cached_document(self, document: ValidatedDocument, cache_dir: Path) -> None:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "validated_document": document.model_dump(mode="json"),
            }
            cache_path = self._cache_path(document.pdf_hash, cache_dir)
            cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to write ingestion cache: %s", exc)
    
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
            document_id=self._resolve_document_id(validation_result.pdf_hash),
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
        
        # Cache the DoclingDocument for downstream use (e.g., metadata extraction)
        if 'docling_document' in extraction_result:
            document.docling_document = extraction_result['docling_document']
        
        return document

    @staticmethod
    def _resolve_document_id(pdf_hash: Optional[str]) -> UUID:
        """
        Build a stable document UUID from the PDF hash.

        This keeps the same ``document_id`` across repeated ingests of the
        same file, enabling Qdrant's existing document-level dedup safeguards
        to skip or overwrite rather than creating duplicate vectors.
        """
        if pdf_hash:
            return uuid5(NAMESPACE_URL, f"pdf:{pdf_hash.lower()}")
        return uuid4()
    
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
            except DeduplicationSkipped as e:
                logger.info("Skipped duplicate PDF %s (hash=%s)", pdf_path, e.pdf_hash)
                failed.append((pdf_path, f"deduplicated:{e.pdf_hash}"))
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
