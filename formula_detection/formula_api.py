from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image
from transformers import TrOCRProcessor
from optimum.onnxruntime import ORTModelForVision2Seq
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import io
import os
from typing import List
from pathlib import Path

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Formula Detection & Analysis API",
    description="Extract LaTeX formulas from images and generate descriptions with variable definitions",
    version="1.0.0"
)

# Pydantic models for structured output
class Variable(BaseModel):
    symbol: str = Field(..., description="The mathematical symbol used in the equation")
    name: str = Field(..., description="The name of the variable")
    details: str = Field(..., description="Detailed description of what the variable represents")

class FormulaOutput(BaseModel):
    description: str = Field(..., description="A simple explanation of the formula")
    variables: List[Variable] = Field(..., description="List of variables used in the equation")

class FormulaResult(BaseModel):
    latex_formula: str = Field(..., description="The extracted LaTeX formula")
    description: str = Field(..., description="Simple explanation of the formula")
    variables: List[Variable] = Field(..., description="List of variables with definitions")

# Global models (loaded once at startup)
processor = None
model = None
llm_chain = None

@app.on_event("startup")
async def load_models():
    """Load models on startup"""
    global processor, model, llm_chain
    
    print("Loading pix2text-mfr model...")
    processor = TrOCRProcessor.from_pretrained('breezedeus/pix2text-mfr')
    model = ORTModelForVision2Seq.from_pretrained('breezedeus/pix2text-mfr', use_cache=False)
    
    print("Setting up LLM chain...")
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
    llm_chain = prompt | llm_model | parser
    
    print("Models loaded successfully!")

def process_single_image(image: Image.Image) -> FormulaResult:
    """Process a single image and return formula analysis"""
    # Convert image to RGB if needed
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Extract LaTeX formula using pix2text-mfr
    pixel_values = processor(images=[image], return_tensors="pt").pixel_values
    generated_ids = model.generate(pixel_values)
    latex_formula = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
    
    # Generate description and variables using LLM
    parser = PydanticOutputParser(pydantic_object=FormulaOutput)
    result = llm_chain.invoke({
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
        result = process_single_image(image)
        
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
            result = process_single_image(image)
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
                    result = process_single_image(image)
                    
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

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "models_loaded": processor is not None and model is not None and llm_chain is not None
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
