# Research Paper Assistant

Multi-service platform for rapid research paper analysis with metadata extraction, reading guide generation, and agentic RAG.

## Services

### 1. Fast Extraction API (NEW!) ⚡
**Port**: 8001 | **Docs**: http://localhost:8001/docs

Ultra-fast document processing (20-30s) using Docling + Groq LLM:
- PDF upload and metadata extraction
- Automatic reading guide generation
- SQL-based deduplication (cached loads <1s)
- RESTful API with 10 endpoints

```bash
# Start service
python fast_extraction_api.py

# Extract document
curl -X POST http://localhost:8001/extract -F "file=@paper.pdf"
```

**Documentation**: [API_FAST_EXTRACTION.md](Documentation/API_FAST_EXTRACTION.md)

---

### 2. Metadata Extraction API
**Port**: 8000 | **Docs**: http://localhost:8000/docs

Original metadata extraction service with detailed analysis.

## Setup

```bash
# Create .env file with the following keys:
GROQ_API_KEY=your_groq_api_key_here

LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT='https://api.smith.langchain.com'
LANGCHAIN_API_KEY='your_langchain_api_key_here'
LANGCHAIN_PROJECT='ResearchAgent'

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
