"""
FastAPI application for Research Paper Metadata Extraction.

This API provides endpoints to extract metadata from research paper PDFs.
"""

import os
import shutil
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from metadata_extraction.src.extractor import extract_paper_metadata
from metadata_extraction.src.models import PaperMetadata, SectionMetadata, PaperInference
from dotenv import load_dotenv
import config

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="Research Paper Metadata Extractor API",
    description="API for extracting structured metadata from research papers",
    version="1.0.0"
)

# Add CORS middleware to allow Streamlit frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create upload directory if it doesn't exist
config.UPLOAD_DIR.mkdir(exist_ok=True)


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Research Paper Metadata Extractor API",
        "version": "1.0.0",
        "endpoints": {
            "/extract": "POST - Extract metadata from PDF",
            "/health": "GET - Health check"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    return {
        "status": "healthy",
        "groq_api_configured": groq_api_key is not None and len(groq_api_key) > 0
    }


@app.post("/extract", response_model=PaperMetadata)
async def extract_metadata(file: UploadFile = File(...)):
    """
    Extract metadata from an uploaded research paper PDF.
    
    Args:
        file: Uploaded PDF file
        
    Returns:
        PaperMetadata object containing:
            - title: Paper title
            - abstract: Paper abstract
            - sections: List of sections with normalized names
            - inference: LLM-inferred properties (type, difficulty, math_heavy)
            
    Raises:
        HTTPException: If extraction fails or file is invalid
    """
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF files are accepted."
        )
    
    # Save uploaded file temporarily
    temp_file_path = config.UPLOAD_DIR / file.filename
    
    try:
        # Save uploaded file
        with temp_file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Extract metadata using the existing pipeline
        metadata = extract_paper_metadata(str(temp_file_path))
        
        return metadata
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: {str(e)}"
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}"
        )
    
    finally:
        # Clean up temporary file
        if temp_file_path.exists():
            temp_file_path.unlink()


@app.delete("/cleanup")
async def cleanup_uploads():
    """
    Clean up all uploaded files.
    
    Returns:
        Status message with number of files removed
    """
    if not config.ENABLE_CLEANUP_ENDPOINT:
        raise HTTPException(
            status_code=403,
            detail="Cleanup endpoint is disabled"
        )
    
    try:
        files_removed = 0
        for file_path in config.UPLOAD_DIR.glob("*"):
            if file_path.is_file():
                file_path.unlink()
                files_removed += 1
        
        return {
            "status": "success",
            "files_removed": files_removed
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    
    # Check for GROQ_API_KEY
    if not config.GROQ_API_KEY:
        print("WARNING: GROQ_API_KEY not found in environment variables!")
        print("Please set it in your .env file or environment")
    
    # Run the FastAPI server
    uvicorn.run(
        app,
        host=config.API_HOST,
        port=config.API_PORT,
        log_level=config.LOG_LEVEL.lower(),
        reload=config.API_RELOAD
    )
