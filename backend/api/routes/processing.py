"""
Processing endpoints for metadata extraction.

Handles metadata extraction from validated documents.
"""

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.processing_service import ProcessingService, IntegratedPipeline
from backend.models.metadata import ProcessedDocument, ExtractedMetadata
from backend.config.settings import Settings


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["processing"])

# Initialize services
settings = Settings()
processing_service = ProcessingService()
integrated_pipeline = IntegratedPipeline()


class ProcessRequest(BaseModel):
    """Request model for document processing."""
    pdf_path: str = Field(..., description="Path to PDF file")
    use_fallback: bool = Field(True, description="Use LLM fallback for missing fields")


class ProcessResponse(BaseModel):
    """Response model for metadata extraction."""
    document_id: str = Field(..., description="Document identifier")
    metadata: dict = Field(..., description="Extracted metadata")
    processing_time_seconds: float = Field(..., description="Processing duration")
    success: bool = Field(..., description="Extraction success status")


class BatchProcessRequest(BaseModel):
    """Request model for batch processing."""
    pdf_paths: List[str] = Field(..., description="List of PDF file paths")
    use_fallback: bool = Field(True, description="Use LLM fallback for missing fields")
    continue_on_error: bool = Field(True, description="Continue if one document fails")


class BatchProcessResponse(BaseModel):
    """Response model for batch processing."""
    total: int = Field(..., description="Total number of documents")
    successful: int = Field(..., description="Number of successful extractions")
    failed: int = Field(..., description="Number of failed extractions")
    results: List[ProcessResponse] = Field(..., description="Individual results")


@router.post("/", response_model=ProcessResponse)
async def process_pdf(request: ProcessRequest) -> ProcessResponse:
    """
    Process a PDF file and extract metadata.
    
    **Process:**
    1. Ingests the PDF (validation, extraction, OCR)
    2. Extracts metadata using heuristics
    3. Applies LLM fallback if needed
    4. Returns extracted metadata
    
    **Parameters:**
    - `pdf_path`: Path to the PDF file
    - `use_fallback`: Whether to use LLM fallback for missing fields
    
    **Returns:**
    - Document ID and extracted metadata
    
    **Errors:**
    - 404: PDF file not found
    - 422: Processing failed
    - 500: Internal error
    """
    
    logger.info(f"Processing request for: {request.pdf_path}")
    
    try:
        # Run integrated pipeline (ingestion + metadata extraction)
        validated_doc, processed_doc = integrated_pipeline.ingest_and_process(
            pdf_path=request.pdf_path
        )
        
        # Format response
        metadata = processed_doc.metadata
        
        response = ProcessResponse(
            document_id=str(processed_doc.document_id),
            metadata={
                'title': metadata.title,
                'abstract': metadata.abstract,
                'sections': [
                    {
                        'original_name': s.original_name,
                        'level': s.level,
                        'page_start': s.page_start
                    }
                    for s in metadata.sections
                ],
                'global_stats': {
                    'total_formulas': metadata.global_stats.total_formulas if metadata.global_stats else 0,
                    'total_tables': metadata.global_stats.total_tables if metadata.global_stats else 0,
                    'total_figures': metadata.global_stats.total_figures if metadata.global_stats else 0,
                    'total_pages': metadata.global_stats.total_pages if metadata.global_stats else 0,
                    'total_sections': metadata.global_stats.total_sections if metadata.global_stats else 0,
                } if metadata.global_stats else {},
                'inference': {
                    'paper_type': metadata.inference.paper_type if metadata.inference else "Unknown",
                    'difficulty': metadata.inference.difficulty if metadata.inference else "medium",
                    'math_heavy': metadata.inference.math_heavy if metadata.inference else False,
                } if metadata.inference else {},
                'extraction_method': metadata.extraction_method,
                'fallback_used': metadata.fallback_used,
                'confidence_score': metadata.confidence_score,
                'missing_fields': metadata.missing_fields,
                'field_coverage': metadata.get_field_coverage(),
            },
            processing_time_seconds=processed_doc.processing_time_seconds,
            success=True
        )
        
        logger.info(
            f"Successfully processed: {request.pdf_path} | "
            f"Coverage: {metadata.get_field_coverage():.1%} | "
            f"Fallback: {metadata.fallback_used}"
        )
        
        return response
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {request.pdf_path}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "FILE_NOT_FOUND",
                "message": f"PDF file not found: {request.pdf_path}",
                "details": str(e)
            }
        )
    
    except Exception as e:
        logger.error(f"Processing failed for {request.pdf_path}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "PROCESSING_FAILED",
                "message": "Failed to process document",
                "details": str(e)
            }
        )


@router.post("/batch", response_model=BatchProcessResponse)
async def process_batch(request: BatchProcessRequest) -> BatchProcessResponse:
    """
    Process multiple PDF files and extract metadata.
    
    **Process:**
    1. Processes each PDF through the integrated pipeline
    2. Continues on errors if configured
    3. Returns results for all documents
    
    **Parameters:**
    - `pdf_paths`: List of PDF file paths
    - `use_fallback`: Whether to use LLM fallback
    - `continue_on_error`: Continue if one document fails
    
    **Returns:**
    - Summary statistics and individual results
    
    **Errors:**
    - 422: Batch processing failed
    - 500: Internal error
    """
    
    logger.info(f"Batch processing request for {len(request.pdf_paths)} documents")
    
    try:
        # Process batch
        results = integrated_pipeline.process_batch(
            pdf_paths=request.pdf_paths,
            continue_on_error=request.continue_on_error
        )
        
        # Format results
        formatted_results = []
        successful = 0
        
        for validated_doc, processed_doc in results:
            metadata = processed_doc.metadata
            
            formatted_results.append(ProcessResponse(
                document_id=str(processed_doc.document_id),
                metadata={
                    'title': metadata.title,
                    'abstract': metadata.abstract[:200] + '...' if metadata.abstract and len(metadata.abstract) > 200 else metadata.abstract,
                    'sections': [{'original_name': s.original_name, 'level': s.level, 'page_start': s.page_start} for s in metadata.sections],
                    'extraction_method': metadata.extraction_method,
                    'fallback_used': metadata.fallback_used,
                    'confidence_score': metadata.confidence_score,
                    'field_coverage': metadata.get_field_coverage(),
                },
                processing_time_seconds=processed_doc.processing_time_seconds,
                success=True
            ))
            successful += 1
        
        response = BatchProcessResponse(
            total=len(request.pdf_paths),
            successful=successful,
            failed=len(request.pdf_paths) - successful,
            results=formatted_results
        )
        
        logger.info(
            f"Batch processing completed: {successful}/{len(request.pdf_paths)} successful"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "BATCH_PROCESSING_FAILED",
                "message": "Failed to process batch",
                "details": str(e)
            }
        )


@router.get("/health")
async def health():
    """Health check for processing service."""
    return {
        "status": "healthy",
        "service": "metadata_extraction",
        "fallback_enabled": True,
    }
