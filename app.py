"""
FastAPI application for Research Paper Metadata Extraction.

This API provides endpoints to extract metadata from research paper PDFs.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
# Import both extraction methods
from src.metadata_extraction.src.extractor import extract_paper_metadata
from src.metadata_extraction.src.models import PaperMetadata as SrcPaperMetadata
from src.metadata_extraction.api_src.extractor import extract_metadata
from src.metadata_extraction.api_src.models import PaperMetadata as ApiPaperMetadata
from dotenv import load_dotenv
import config
import io
from PIL import Image

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


# Pydantic models for formula detection
class Variable(BaseModel):
    """Variable in a mathematical formula."""
    symbol: str = Field(..., description="The mathematical symbol used in the equation")
    name: str = Field(..., description="The name of the variable")
    details: str = Field(..., description="Detailed description of what the variable represents")


class FormulaOutput(BaseModel):
    """Output from LLM analysis of a formula."""
    description: str = Field(..., description="A simple explanation of the formula")
    variables: List[Variable] = Field(..., description="List of variables used in the equation")


class FormulaResult(BaseModel):
    """Complete result for a formula analysis."""
    latex_formula: str = Field(..., description="The extracted LaTeX formula")
    description: str = Field(..., description="Simple explanation of the formula")
    variables: List[Variable] = Field(..., description="List of variables with definitions")


# Global models for formula detection (loaded on startup)
formula_processor = None
formula_model = None
formula_llm_chain = None


@app.on_event("startup")
async def load_formula_models():
    """Load formula detection models on startup."""
    global formula_processor, formula_model, formula_llm_chain
    
    try:
        from transformers import TrOCRProcessor
        from optimum.onnxruntime import ORTModelForVision2Seq
        from langchain_groq import ChatGroq
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import PydanticOutputParser
        
        print("Loading pix2text-mfr model for formula detection...")
        formula_processor = TrOCRProcessor.from_pretrained('breezedeus/pix2text-mfr')
        formula_model = ORTModelForVision2Seq.from_pretrained('breezedeus/pix2text-mfr', use_cache=False)
        
        print("Setting up LLM chain for formula analysis...")
        parser = PydanticOutputParser(pydantic_object=FormulaOutput)
        
        prompt_text = """
You are an expert mathematician who also knows latex code.
You are provided with following LaTeX code representing a mathematical equation.
{formula}

Your task is to:
1. Provide a simple explanation of the equation in layman's terms.
2. List and define all variables used in the equation with their symbol, name, and details.

{format_instructions}
"""
        prompt = ChatPromptTemplate.from_template(prompt_text)
        llm_model = ChatGroq(temperature=0.5, model="llama-3.1-8b-instant")
        formula_llm_chain = prompt | llm_model | parser
        
        print("Formula detection models loaded successfully!")
    except Exception as e:
        print(f"Warning: Could not load formula detection models: {e}")
        print("Formula detection endpoints will not be available.")


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Research Paper Metadata Extractor API",
        "version": "1.0.0",
        "endpoints": {
            "Metadata Extraction (PDF-based)": {
                "/extract-src": "POST - Extract metadata from PDF (src pipeline with DB)",
                "/extract-api": "POST - Extract metadata from PDF (api_src pipeline with Qdrant)"
            },
            "Formula Analysis": {
                "/analyze-formula": "POST - Analyze single formula image",
                "/analyze-formulas-batch": "POST - Analyze multiple formula images",
                "/analyze-formulas-folder": "POST - Analyze all formulas in a folder"
            },
            "Utilities": {
                "/health": "GET - Health check",
                "/cleanup": "DELETE - Clean up uploaded files"
            }
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    return {
        "status": "healthy",
        "groq_api_configured": groq_api_key is not None and len(groq_api_key) > 0,
        "formula_models_loaded": formula_processor is not None and formula_model is not None
    }


@app.post("/extract-src", response_model=SrcPaperMetadata)
async def extract_metadata_src(file: UploadFile = File(...), enable_db: bool = True):
    """
    Extract metadata from PDF using src pipeline (with SQLite database).
    
    This endpoint uses the metadata_extraction.src pipeline which:
    - Processes PDF directly
    - Stores results in SQLite database
    - Uses LangGraph for orchestration
    
    Args:
        file: Uploaded PDF file
        enable_db: Whether to store results in database (default: True)
        
    Returns:
        PaperMetadata object with title, abstract, sections, and inference
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF files are accepted."
        )
    
    temp_file_path = config.UPLOAD_DIR / file.filename
    
    try:
        # Save uploaded file
        with temp_file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Extract metadata using src pipeline
        metadata = extract_paper_metadata(str(temp_file_path), enable_db=enable_db)
        
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


@app.post("/extract-api", response_model=ApiPaperMetadata)
async def extract_metadata_api(
    document_id: str,
    collection_name: str = "research_papers_main",
    save_to_file: bool = False
):
    """
    Extract metadata using api_src pipeline (from Qdrant vector database).
    
    This endpoint uses the metadata_extraction.api_src pipeline which:
    - Fetches data from Qdrant vector database
    - Requires document to already be in Qdrant collection
    - Uses LangGraph for orchestration
    
    Args:
        document_id: Document identifier (usually filename)
        collection_name: Qdrant collection name (default: "research_papers_main")
        save_to_file: Whether to save output to JSON file (default: False)
        
    Returns:
        PaperMetadata object with title, abstract, sections, and inference
    """
    try:
        # Extract metadata using api_src pipeline
        metadata = extract_metadata(
            document_id=document_id,
            collection_name=collection_name,
            save_to_file=save_to_file
        )
        
        return metadata
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}"
        )

def process_formula_image(image: Image.Image) -> FormulaResult:
    """
    Process a single formula image and return analysis.
    
    Args:
        image: PIL Image containing a mathematical formula
        
    Returns:
        FormulaResult with LaTeX formula, description, and variables
    """
    if formula_processor is None or formula_model is None or formula_llm_chain is None:
        raise HTTPException(
            status_code=503,
            detail="Formula detection models not loaded. Please restart the server."
        )
    
    # Convert image to RGB if needed
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Extract LaTeX formula using pix2text-mfr
    pixel_values = formula_processor(images=[image], return_tensors="pt").pixel_values
    generated_ids = formula_model.generate(pixel_values)
    latex_formula = formula_processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
    
    # Generate description and variables using LLM
    from langchain_core.output_parsers import PydanticOutputParser
    parser = PydanticOutputParser(pydantic_object=FormulaOutput)
    result = formula_llm_chain.invoke({
        "formula": latex_formula,
        "format_instructions": parser.get_format_instructions()
    })
    
    return FormulaResult(
        latex_formula=latex_formula,
        description=result.description,
        variables=result.variables
    )


@app.post("/analyze-formula", response_model=FormulaResult)
async def analyze_formula(file: UploadFile = File(...)):
    """
    Analyze a single formula image.
    
    Args:
        file: Image file containing a mathematical formula
        
    Returns:
        FormulaResult with LaTeX formula, description, and variables
    """
    try:
        # Read and validate image
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))
        
        # Process the image
        result = process_formula_image(image)
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")


@app.post("/analyze-formulas-batch", response_model=List[FormulaResult])
async def analyze_formulas_batch(files: List[UploadFile] = File(...)):
    """
    Analyze multiple formula images in batch.
    
    Args:
        files: List of image files containing mathematical formulas
        
    Returns:
        List of FormulaResult objects
    """
    try:
        results = []
        
        for file in files:
            # Read image
            contents = await file.read()
            image = Image.open(io.BytesIO(contents))
            
            # Process the image
            result = process_formula_image(image)
            results.append(result)
        
        return results
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing images: {str(e)}")


@app.post("/analyze-formulas-folder")
async def analyze_formulas_folder(folder_path: str):
    """
    Analyze all formula images in a folder.
    
    Args:
        folder_path: Path to folder containing formula images
        
    Returns:
        List of FormulaResult objects with filenames
    """
    try:
        folder = Path(folder_path)
        
        if not folder.exists() or not folder.is_dir():
            raise HTTPException(status_code=400, detail="Invalid folder path")
        
        # Supported image extensions
        image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
        
        results = []
        
        # Process all images in folder
        for image_path in folder.iterdir():
            if image_path.suffix.lower() in image_extensions:
                try:
                    image = Image.open(image_path)
                    result = process_formula_image(image)
                    
                    results.append({
                        "filename": image_path.name,
                        "latex_formula": result.latex_formula,
                        "description": result.description,
                        "variables": [var.dict() for var in result.variables]
                    })
                except Exception as e:
                    results.append({
                        "filename": image_path.name,
                        "error": str(e)
                    })
        
        return JSONResponse(content={"results": results, "total": len(results)})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing folder: {str(e)}")



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
