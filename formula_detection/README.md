# Formula Detection & Analysis API

A FastAPI-based service that extracts LaTeX formulas from images and generates descriptions with variable definitions using the pix2text-mfr model and LLM analysis.

## Features

- **Single Image Analysis**: Upload one formula image for analysis
- **Batch Processing**: Upload multiple images at once
- **Folder Processing**: Analyze all images in a specified folder
- **Structured Output**: Returns LaTeX formula, description, and variable definitions

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
Create a `.env` file with your Groq API key:
```
GROQ_API_KEY=your_api_key_here
```

## Running the API

Start the server:
```bash
python formula_api.py
```

Or using uvicorn directly:
```bash
uvicorn formula_api:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## API Endpoints

### 1. Analyze Single Formula
**POST** `/analyze-formula`

Upload a single image containing a mathematical formula.

**Request:**
- Form data with file upload
- Key: `file`
- Value: Image file (PNG, JPG, JPEG, etc.)

**Response:**
```json
{
  "latex_formula": "E = mc^2",
  "description": "This is Einstein's mass-energy equivalence equation...",
  "variables": [
    {
      "symbol": "E",
      "name": "Energy",
      "details": "The energy of an object"
    },
    {
      "symbol": "m",
      "name": "Mass",
      "details": "The mass of the object"
    },
    {
      "symbol": "c",
      "name": "Speed of light",
      "details": "The speed of light in vacuum"
    }
  ]
}
```

### 2. Analyze Multiple Formulas (Batch)
**POST** `/analyze-formulas-batch`

Upload multiple images for batch processing.

**Request:**
- Form data with multiple file uploads
- Key: `files`
- Value: Multiple image files

**Response:**
```json
[
  {
    "latex_formula": "...",
    "description": "...",
    "variables": [...]
  },
  {
    "latex_formula": "...",
    "description": "...",
    "variables": [...]
  }
]
```

### 3. Analyze Formulas from Folder
**POST** `/analyze-formulas-folder`

Analyze all formula images in a specified folder path.

**Request:**
```json
{
  "folder_path": "/path/to/formulas/folder"
}
```

**Response:**
```json
{
  "results": [
    {
      "filename": "formula1.png",
      "latex_formula": "...",
      "description": "...",
      "variables": [...]
    },
    {
      "filename": "formula2.png",
      "latex_formula": "...",
      "description": "...",
      "variables": [...]
    }
  ],
  "total": 2
}
```

### 4. Health Check
**GET** `/health`

Check if the API and models are loaded correctly.

**Response:**
```json
{
  "status": "healthy",
  "models_loaded": true
}
```

## Example Usage

### Using cURL

**Single image:**
```bash
curl -X POST "http://localhost:8000/analyze-formula" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@formula.png"
```

**Multiple images:**
```bash
curl -X POST "http://localhost:8000/analyze-formulas-batch" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "files=@formula1.png" \
  -F "files=@formula2.png" \
  -F "files=@formula3.png"
```

**Folder analysis:**
```bash
curl -X POST "http://localhost:8000/analyze-formulas-folder" \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "/path/to/formulas"}'
```

### Using Python requests

```python
import requests

# Single image
with open('formula.png', 'rb') as f:
    files = {'file': f}
    response = requests.post('http://localhost:8000/analyze-formula', files=files)
    result = response.json()
    print(result)

# Multiple images
files = [
    ('files', open('formula1.png', 'rb')),
    ('files', open('formula2.png', 'rb')),
    ('files', open('formula3.png', 'rb'))
]
response = requests.post('http://localhost:8000/analyze-formulas-batch', files=files)
results = response.json()
print(results)

# Folder
response = requests.post(
    'http://localhost:8000/analyze-formulas-folder',
    json={"folder_path": "/path/to/formulas"}
)
results = response.json()
print(results)
```

## Interactive Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Models Used

- **pix2text-mfr**: Mathematical formula recognition model for LaTeX extraction
- **llama-3.1-8b-instant**: LLM for generating descriptions and variable definitions (via Groq)

## Output Structure

Each formula analysis returns:
- `latex_formula`: The extracted LaTeX code
- `description`: A simple explanation in layman's terms
- `variables`: List of variables with:
  - `symbol`: Mathematical symbol
  - `name`: Variable name
  - `details`: Detailed description

## Notes

- The API loads models on startup, which may take a few seconds
- Ensure your Groq API key is properly configured
- Supported image formats: PNG, JPG, JPEG, BMP, TIFF
- For folder processing, provide absolute paths
