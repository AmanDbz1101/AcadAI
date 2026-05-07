"""
Metadata extraction pipeline.

Orchestrates the complete metadata extraction workflow using
Docling + Groq approach for accurate extraction.
"""

import time
import logging
from pathlib import Path
from typing import Optional

from backend.extraction.models.document import ValidatedDocument
from backend.extraction.models.metadata import ExtractedMetadata, ProcessedDocument
from backend.extraction.app.groq_fallback import GroqFallbackExtractor
from backend.extraction.app.metadata_extractor import MetadataExtractor
from dotenv import load_dotenv
load_dotenv()

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


def _trace_metadata_stage(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    safe_stage = _safe_trace_stage_name(stage)
    runner = _TRACE_RUNNER_CACHE.get(safe_stage)
    if runner is None:
        @traceable(name=f"metadata_stage:{safe_stage}", run_type="chain")
        def _runner(event_payload: dict[str, Any]) -> dict[str, Any]:
            return event_payload

        runner = _runner
        _TRACE_RUNNER_CACHE[safe_stage] = runner

    return runner({"stage": stage, **payload})


class MetadataExtractionPipeline:
    """
    Orchestrates metadata extraction from validated documents.
    
    Uses Docling for structure extraction and Groq LLM for classification.
    """
    
    def __init__(
        self,
        groq_api_key: Optional[str] = None,
    ):
        """
        Initialize metadata extraction pipeline.
        
        Args:
            groq_api_key: Groq API key for LLM (defaults to env var)
        """
        # Initialize extractor
        self.extractor = MetadataExtractor(api_key=groq_api_key)
        self.groq_fallback: Optional[GroqFallbackExtractor] = None
        fallback_key = groq_api_key or self.extractor.api_key
        if fallback_key:
            try:
                self.groq_fallback = GroqFallbackExtractor(api_key=fallback_key)
            except Exception as exc:
                logger.warning("Groq fallback unavailable: %s", exc)

    def _recover_missing_title_abstract(
        self,
        document: ValidatedDocument,
        metadata: ExtractedMetadata,
    ) -> ExtractedMetadata:
        """Recover missing title/abstract using Groq from the first few pages."""
        needs_title = not self.extractor._is_valid_title(metadata.title or "")
        needs_abstract = not self.extractor._is_valid_abstract(metadata.abstract or "")

        if not self.groq_fallback or not (needs_title or needs_abstract):
            return metadata

        missing_fields = []
        if needs_title:
            missing_fields.append("title")
        if needs_abstract:
            missing_fields.append("abstract")

        llm_extracted = self.groq_fallback.extract_missing_fields(
            document=document,
            missing_fields=missing_fields,
            existing_metadata=metadata,
        )
        if not llm_extracted:
            return metadata

        merged = self.groq_fallback.merge_with_existing(metadata, llm_extracted)
        merged.missing_fields = self.extractor._identify_missing_fields(
            {
                "title": merged.title,
                "abstract": merged.abstract,
                "keywords": merged.keywords,
                "sections": merged.sections,
            }
        )
        merged.confidence_score = merged.get_field_coverage()
        return merged
    
    def process(self, document: ValidatedDocument) -> ProcessedDocument:
        """
        Process a validated document to extract metadata.
        
        Args:
            document: ValidatedDocument from ingestion pipeline
            
        Returns:
            ProcessedDocument with extracted metadata
        """
        logger.info(f"Starting metadata extraction for document {document.document_id}")
        _trace_metadata_stage("start", {"document_id": str(document.document_id)})
        start_time = time.time()
        
        # Extract metadata using Docling + Groq approach
        try:
            logger.info("MetadataPipeline: passing pre-converted document to extractor")
            metadata = self.extractor.extract(document, preconverted_doc=document.docling_document)
        except Exception as exc:
            logger.warning("Primary metadata extraction failed, attempting first-page Groq fallback: %s", exc)
            _trace_metadata_stage("extract_failure", {"document_id": str(document.document_id), "error": str(exc)})
            metadata = ExtractedMetadata()

        metadata = self._recover_missing_title_abstract(document, metadata)
        
        # Create processed document
        processing_time = time.time() - start_time
        
        processed_doc = ProcessedDocument(
            document_id=document.document_id,
            metadata=metadata,
            processing_time_seconds=processing_time
        )
        
        logger.info(
            f"Metadata extraction completed in {processing_time:.2f}s. "
            f"Coverage: {metadata.get_field_coverage():.2%}"
        )
        _trace_metadata_stage("completed", {
            "document_id": str(document.document_id),
            "processing_time": processing_time,
            "fields_found": len(getattr(metadata, 'sections', []) or []),
        })
        
        return processed_doc
    
    def process_batch(
        self,
        documents: list[ValidatedDocument],
        continue_on_error: bool = True
    ) -> list[ProcessedDocument]:
        """
        Process multiple documents.
        
        Args:
            documents: List of ValidatedDocuments
            continue_on_error: Whether to continue if one document fails
            
        Returns:
            List of ProcessedDocuments
        """
        results = []
        
        logger.info(f"Processing batch of {len(documents)} documents")
        
        for i, document in enumerate(documents, 1):
            try:
                logger.info(f"Processing document {i}/{len(documents)}")
                processed = self.process(document)
                results.append(processed)
                
            except Exception as e:
                logger.error(f"Error processing document {document.document_id}: {e}")
                
                if not continue_on_error:
                    raise
                
                # Create a failed result
                results.append(ProcessedDocument(
                    document_id=document.document_id,
                    metadata=ExtractedMetadata(),
                    processing_time_seconds=0
                ))
        
        logger.info(f"Batch processing completed: {len(results)}/{len(documents)} successful")
        
        return results
