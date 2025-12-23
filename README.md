# Research Paper Metadata Extractor

FastAPI service that extracts structured metadata from research paper PDFs.

## Setup

```bash
# Create .env file with your API key
GROQ_API_KEY=your_key_here

# Install dependencies
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

API runs at: http://localhost:8000

## Usage

1. Open http://localhost:8000/docs
2. Click on `POST /extract` endpoint
3. Click "Try it out"
4. Upload your PDF file
5. Click "Execute"
6. Get JSON response with:
   - Paper title
   - Abstract
   - Sections with page numbers
   - Paper type, difficulty, math-heavy indicator

## Example Output

```json
{
  "title": "Paper Title",
  "abstract": "Paper abstract text...",
  "sections": [
    {"original_name": "1. Introduction", "page_start": 1},
    {"original_name": "2. Methods", "page_start": 3}
  ],
  "inference": {
    "paper_type": "Empirical",
    "difficulty": "medium",
    "math_heavy": false
  }
}
```
