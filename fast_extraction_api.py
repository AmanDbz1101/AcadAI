"""
FastAPI Application for Fast Document Extraction

Endpoints:
- POST /extract - Upload and process PDF
- GET /status/{document_id} - Check processing status
- GET /metadata/{document_id} - Get metadata JSON
- GET /guide/{document_id} - Get reading guide JSON
- GET /documents - List all documents
- GET /statistics - Get database statistics
- POST /reprocess/{document_id} - Force reprocess document
- DELETE /document/{document_id} - Delete document
"""

import os
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from src.fast_extraction.pipeline import FastExtractionPipeline
from src.fast_extraction.models import DocumentStatus

# Initialize FastAPI app
app = FastAPI(
    title="Fast Document Extraction API",
    description="Rapid research paper metadata extraction and guide generation",
    version="1.0.0"
)

# Initialize pipeline
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("output")
DB_PATH = "fast_extraction_docs.db"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

pipeline = FastExtractionPipeline(
    db_path=DB_PATH,
    output_dir=str(OUTPUT_DIR)
)


# Response models
class ExtractionResponse(BaseModel):
    """Response from document extraction"""
    document_id: str
    status: str
    title: str
    abstract: str
    sections_count: int
    total_pages: int
    is_cached: bool
    metadata_path: str
    guide_path: Optional[str] = None
    processing_time_seconds: Optional[float] = None


class StatusResponse(BaseModel):
    """Document processing status"""
    document_id: str
    title: str
    status: str
    docling_ready: bool
    api_ready: bool
    docling_metadata_path: Optional[str]
    api_metadata_path: Optional[str]
    vectorstore_collection: Optional[str]
    created_at: Optional[str]


class DocumentInfo(BaseModel):
    """Brief document information"""
    document_id: str
    title: str
    status: str
    created_at: Optional[str]


class StatisticsResponse(BaseModel):
    """Database statistics"""
    total: int
    processing: int
    docling_ready: int
    api_complete: int
    failed: int


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None


# Helper function for background processing
async def process_document_bg(pdf_path: str, document_id: str = None):
    """Background task for document processing"""
    try:
        doc_id, metadata, is_cached = pipeline.process_document(
            pdf_path=pdf_path,
            force_reprocess=False
        )
        
        # Generate guide if not cached
        if not is_cached:
            pipeline.generate_guide(doc_id)
        
        return doc_id, metadata, is_cached
    except Exception as e:
        print(f"Background processing failed: {e}")
        raise


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "message": "Fast Document Extraction API",
        "version": "1.0.0",
        "endpoints": {
            "extract": "POST /extract",
            "status": "GET /status/{document_id}",
            "metadata": "GET /metadata/{document_id}",
            "guide": "GET /guide/{document_id}",
            "documents": "GET /documents",
            "statistics": "GET /statistics"
        }
    }


@app.post("/extract", response_model=ExtractionResponse, tags=["Extraction"])
async def extract_document(
    file: UploadFile = File(...),
    generate_guide: bool = Query(True, description="Generate reading guide automatically"),
    force_reprocess: bool = Query(False, description="Force reprocess even if cached")
):
    """
    Extract metadata from uploaded PDF
    
    - **file**: PDF file to process
    - **generate_guide**: Whether to generate reading guide (default: true)
    - **force_reprocess**: Force reprocess even if document exists (default: false)
    
    Returns document metadata and processing status
    """
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Save uploaded file
    upload_path = UPLOAD_DIR / file.filename
    try:
        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Process document
    try:
        start_time = datetime.now()
        
        document_id, metadata, is_cached = pipeline.process_document(
            pdf_path=str(upload_path),
            force_reprocess=force_reprocess
        )
        
        # Generate guide if requested and not cached
        guide_path = None
        if generate_guide and not is_cached:
            guide_path = pipeline.generate_guide(document_id)
        elif generate_guide and is_cached:
            # Check if guide already exists
            potential_guide_path = OUTPUT_DIR / f"{document_id}_guide.json"
            if potential_guide_path.exists():
                guide_path = str(potential_guide_path)
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        return ExtractionResponse(
            document_id=document_id,
            status="completed",
            title=metadata.paper_title,
            abstract=metadata.abstract[:200] + "..." if len(metadata.abstract) > 200 else metadata.abstract,
            sections_count=len(metadata.sections),
            total_pages=metadata.global_stats.total_pages,
            is_cached=is_cached,
            metadata_path=f"/metadata/{document_id}",
            guide_path=f"/guide/{document_id}" if guide_path else None,
            processing_time_seconds=processing_time if not is_cached else None
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@app.get("/status/{document_id}", response_model=StatusResponse, tags=["Query"])
async def get_status(document_id: str):
    """
    Get document processing status
    
    - **document_id**: UUID of the document
    
    Returns current processing status and metadata paths
    """
    status = pipeline.get_document_status(document_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return StatusResponse(**status)


@app.get("/metadata/{document_id}", tags=["Query"])
async def get_metadata(document_id: str):
    """
    Get document metadata JSON
    
    - **document_id**: UUID of the document
    
    Returns the full metadata JSON file
    """
    status = pipeline.get_document_status(document_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not status.get("docling_metadata_path"):
        raise HTTPException(status_code=404, detail="Metadata not available yet")
    
    metadata_path = Path(status["docling_metadata_path"])
    
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Metadata file not found")
    
    return FileResponse(
        path=str(metadata_path),
        media_type="application/json",
        filename=f"{document_id}_metadata.json"
    )


@app.get("/guide/{document_id}", tags=["Query"])
async def get_guide(document_id: str):
    """
    Get reading guide JSON
    
    - **document_id**: UUID of the document
    
    Returns the reading guide JSON file
    """
    guide_path = OUTPUT_DIR / f"{document_id}_guide.json"
    
    if not guide_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Guide not found. Use POST /extract with generate_guide=true"
        )
    
    return FileResponse(
        path=str(guide_path),
        media_type="application/json",
        filename=f"{document_id}_guide.json"
    )


@app.get("/documents", response_model=List[DocumentInfo], tags=["Query"])
async def list_documents(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: Optional[int] = Query(None, description="Maximum number of results")
):
    """
    List all processed documents
    
    - **status**: Filter by status (processing, docling_ready, api_complete, failed)
    - **limit**: Maximum number of results
    
    Returns list of documents with basic information
    """
    try:
        # Convert string status to enum if provided
        status_enum = None
        if status:
            try:
                status_enum = DocumentStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {[s.value for s in DocumentStatus]}"
                )
        
        docs = pipeline.list_documents(status=status_enum, limit=limit)
        return [DocumentInfo(**doc) for doc in docs]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/statistics", response_model=StatisticsResponse, tags=["Query"])
async def get_statistics():
    """
    Get database statistics
    
    Returns counts of documents by status
    """
    stats = pipeline.get_statistics()
    return StatisticsResponse(**stats)


@app.post("/reprocess/{document_id}", response_model=ExtractionResponse, tags=["Extraction"])
async def reprocess_document(
    document_id: str,
    generate_guide: bool = Query(True, description="Generate reading guide")
):
    """
    Force reprocess an existing document
    
    - **document_id**: UUID of the document to reprocess
    - **generate_guide**: Whether to generate reading guide
    
    Useful for updating metadata with new extraction logic
    """
    # Get document record
    record = pipeline.db.get_document_by_id(document_id)
    
    if not record:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Find original PDF (check uploads directory)
    pdf_path = None
    for upload_file in UPLOAD_DIR.glob("*.pdf"):
        # Compute hash and compare
        file_hash = pipeline.db.compute_pdf_hash(str(upload_file))
        if file_hash == record.pdf_hash:
            pdf_path = upload_file
            break
    
    if not pdf_path:
        raise HTTPException(
            status_code=404,
            detail="Original PDF not found in uploads directory"
        )
    
    # Reprocess
    try:
        start_time = datetime.now()
        
        doc_id, metadata, _ = pipeline.process_document(
            pdf_path=str(pdf_path),
            force_reprocess=True
        )
        
        # Generate guide
        guide_path = None
        if generate_guide:
            guide_path = pipeline.generate_guide(doc_id)
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        return ExtractionResponse(
            document_id=doc_id,
            status="completed",
            title=metadata.paper_title,
            abstract=metadata.abstract[:200] + "..." if len(metadata.abstract) > 200 else metadata.abstract,
            sections_count=len(metadata.sections),
            total_pages=metadata.global_stats.total_pages,
            is_cached=False,
            metadata_path=f"/metadata/{doc_id}",
            guide_path=f"/guide/{doc_id}" if guide_path else None,
            processing_time_seconds=processing_time
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reprocessing failed: {str(e)}")


@app.delete("/document/{document_id}", tags=["Management"])
async def delete_document(document_id: str):
    """
    Delete document from database and remove files
    
    - **document_id**: UUID of the document to delete
    
    Removes database record and associated files
    """
    # Get document record
    record = pipeline.db.get_document_by_id(document_id)
    
    if not record:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete files
    deleted_files = []
    
    if record.docling_metadata_path:
        metadata_path = Path(record.docling_metadata_path)
        if metadata_path.exists():
            metadata_path.unlink()
            deleted_files.append(str(metadata_path))
    
    guide_path = OUTPUT_DIR / f"{document_id}_guide.json"
    if guide_path.exists():
        guide_path.unlink()
        deleted_files.append(str(guide_path))
    
    # Delete from database
    success = pipeline.db.delete_document(document_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete from database")
    
    return {
        "message": "Document deleted successfully",
        "document_id": document_id,
        "deleted_files": deleted_files
    }


@app.get("/health", tags=["Root"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "database": "connected",
        "pipeline": "ready"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
