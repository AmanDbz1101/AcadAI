"""
Upload endpoint for PDF ingestion.

Handles file uploads and triggers the ingestion pipeline.
"""

import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.services.ingestion_service import IngestionService
from backend.pipelines.ingest_pipeline import IngestionError, ValidationError
from backend.config.settings import Settings


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])

# Initialize service (will be properly injected in production)
settings = Settings()
ingestion_service = IngestionService(
    cache_dir=settings.CACHE_DIR if settings.ENABLE_CACHE else None,
    enable_deduplication=True,
)


class UploadResponse(BaseModel):
    """Response model for file upload."""
    document_id: UUID = Field(..., description="Unique document identifier")
    filename: str = Field(..., description="Original filename")
    status: str = Field(..., description="Processing status")
    page_count: int = Field(..., description="Number of pages")
    processing_time_seconds: float = Field(..., description="Processing duration")
    ocr_applied: bool = Field(..., description="Whether OCR was used")
    message: str = Field(..., description="Status message")


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")


@router.post("/", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(..., description="PDF file to upload"),
    force_ocr: bool = False,
) -> UploadResponse:
    """
    Upload and process a PDF file.
    
    **Process:**
    1. Validates the uploaded file
    2. Extracts text and layout signals
    3. Applies OCR if needed (or forced)
    4. Returns document metadata
    
    **Parameters:**
    - `file`: PDF file (max size configured in settings)
    - `force_ocr`: Force OCR processing regardless of text density
    
    **Returns:**
    - Document ID and processing metadata
    
    **Errors:**
    - 400: Invalid file (wrong format, corrupted, too large)
    - 422: Validation failed
    - 500: Processing error
    """
    
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_FILE_TYPE",
                "message": "Only PDF files are allowed",
                "details": f"Received: {file.filename}"
            }
        )
    
    logger.info(f"Received upload: {file.filename}")
    
    # Save uploaded file temporarily
    upload_path = settings.UPLOAD_DIR / file.filename
    try:
        # Ensure upload directory exists
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save file
        with open(upload_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.debug(f"Saved to: {upload_path}")
        
    except Exception as e:
        logger.error(f"Failed to save upload: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "SAVE_FAILED",
                "message": "Failed to save uploaded file",
                "details": str(e)
            }
        )
    
    # Check for duplicates
    duplicate_id = ingestion_service.is_duplicate(upload_path)
    if duplicate_id:
        logger.info(f"Duplicate detected: {file.filename} -> {duplicate_id}")
        # Clean up duplicate file
        upload_path.unlink(missing_ok=True)
        
        return JSONResponse(
            status_code=200,
            content={
                "document_id": str(duplicate_id),
                "filename": file.filename,
                "status": "duplicate",
                "message": "Document already processed (duplicate detected)",
            }
        )
    
    # Process through ingestion pipeline
    try:
        document = ingestion_service.ingest(
            pdf_path=upload_path,
            force_ocr=force_ocr,
        )
        
        logger.info(
            f"Successfully processed: {file.filename} -> {document.document_id}"
        )
        
        # Build response
        response = UploadResponse(
            document_id=document.document_id,
            filename=file.filename,
            status=document.status.value,
            page_count=document.page_count,
            processing_time_seconds=document.processing_time_seconds,
            ocr_applied=document.ocr_metadata.was_ocr_applied if document.ocr_metadata else False,
            message="Document processed successfully"
        )
        
        return response
        
    except ValidationError as e:
        logger.warning(f"Validation failed: {str(e)}")
        # Clean up failed upload
        upload_path.unlink(missing_ok=True)
        
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION_FAILED",
                "message": str(e),
                "details": "PDF validation failed - file may be corrupted or invalid"
            }
        )
        
    except IngestionError as e:
        logger.error(f"Ingestion failed: {str(e)}")
        # Clean up failed upload
        upload_path.unlink(missing_ok=True)
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INGESTION_FAILED",
                "message": str(e),
                "details": "Failed to process PDF - see logs for details"
            }
        )
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        # Clean up failed upload
        upload_path.unlink(missing_ok=True)
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": str(e) if settings.ENABLE_DETAILED_ERRORS else None
            }
        )


@router.get("/status/{document_id}")
async def get_document_status(document_id: UUID):
    """
    Get processing status for a document.
    
    **Parameters:**
    - `document_id`: Document UUID
    
    **Returns:**
    - Document status and metadata
    
    **Note:** This is a placeholder - implement with proper storage backend
    """
    # TODO: Implement with actual document storage/database
    raise HTTPException(
        status_code=501,
        detail={
            "error": "NOT_IMPLEMENTED",
            "message": "Status tracking not yet implemented",
            "details": "Coming in next version"
        }
    )


@router.get("/health")
async def health_check():
    """
    Health check endpoint for ingestion service.
    
    **Returns:**
    - Service health status
    """
    stats = ingestion_service.get_stats()
    
    return {
        "status": "healthy",
        "service": "ingestion",
        "stats": stats,
    }
