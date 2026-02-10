# 🚀 Quick Start Guide - PDF Ingestion Module

## Prerequisites

- Python 3.10+ 
- pip package manager
- A PDF file to test with

## Step 1: Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

**Required packages:**
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pydantic` - Data validation
- `pymupdf` - PDF validation
- `docling` - Text extraction
- `python-multipart` - File uploads

## Step 2: Configure Environment (Optional)

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings (optional - defaults work fine)
nano .env
```

## Step 3: Run the API Server

### Option A: Using the main script
```bash
python backend/main.py
```

### Option B: Using uvicorn directly
```bash
cd backend
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

### Option C: From project root
```bash
python -m backend.main
```

The server will start at: **http://localhost:8000**

## Step 4: Test the API

### View API Documentation
Open in browser:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Upload a PDF via cURL
```bash
curl -X POST "http://localhost:8000/upload/" \
  -F "file=@your_paper.pdf"
```

### Upload with Python requests
```python
import requests

with open("your_paper.pdf", "rb") as f:
    files = {"file": f}
    response = requests.post("http://localhost:8000/upload/", files=files)
    print(response.json())
```

### Check Service Health
```bash
curl http://localhost:8000/upload/health
```

## Step 5: Use Programmatically (No API)

### Quick Test
```bash
python backend/test_ingestion.py
```

### Run Examples
```bash
python backend/examples/ingestion_usage.py
```

### Custom Script
```python
from pathlib import Path
from backend.pipelines import IngestPipeline

# Initialize pipeline
pipeline = IngestPipeline()

# Process a PDF
document = pipeline.process(Path("paper.pdf"))

# Access results
print(f"Pages: {document.page_count}")
print(f"Words: {document.total_word_count:,}")
print(f"First 200 chars: {document.full_text[:200]}")
```

## Common Tasks

### Process with Forced OCR
```bash
curl -X POST "http://localhost:8000/upload/?force_ocr=true" \
  -F "file=@scanned_paper.pdf"
```

### Validate PDF Only (No Processing)
```python
from backend.app.ingestion import PDFValidator

validator = PDFValidator(max_file_size_mb=50)
result = validator.validate(Path("paper.pdf"))

if result.is_valid:
    print(f"Valid: {result.page_count} pages")
else:
    for error in result.errors:
        print(f"Error: {error.message}")
```

### Check Readability (Needs OCR?)
```python
from backend.app.ingestion import PDFLoader

loader = PDFLoader()
result = loader.load(Path("paper.pdf"))

readability = loader.detect_readability(result['pages'])
print(readability['recommendation'])
```

### Batch Process Multiple PDFs
```python
from pathlib import Path
from backend.pipelines import IngestPipeline

pipeline = IngestPipeline()
pdf_files = list(Path("papers/").glob("*.pdf"))

results = pipeline.process_batch(pdf_files, continue_on_error=True)
print(f"Successful: {len(results['successful'])}")
print(f"Failed: {len(results['failed'])}")
```

## Expected Output

### Successful Upload Response
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "paper.pdf",
  "status": "completed",
  "page_count": 15,
  "processing_time_seconds": 8.5,
  "ocr_applied": false,
  "message": "Document processed successfully"
}
```

### Processing Times
- **Digital PDF** (15 pages): 5-10 seconds
- **Scanned PDF** (15 pages): 15-30 seconds  
- **Large PDF** (100 pages): 30-60 seconds

## Troubleshooting

### Module Not Found Error
```bash
# Ensure you're in the correct directory
cd /path/to/Research Paper Assistant

# Or add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Docling Import Error
```bash
pip install docling docling-core
```

### PyMuPDF Error
```bash
pip install pymupdf
```

### Port Already in Use
```bash
# Change port in .env or use command line
uvicorn backend.api.app:app --port 8001
```

### File Upload Too Large
Edit `.env`:
```bash
MAX_FILE_SIZE_MB=100  # Increase limit
```

## Directory Structure Created

After first run, these directories will be created:
```
├── uploads/     # Temporary uploaded files
├── logs/        # Application logs
└── cache/       # Cached documents (if enabled)
```

## Next Steps

1. ✅ **Module 1 Complete** - PDF Ingestion working
2. 🔄 **Coming Next** - Module 2: Document Processing
3. 📝 **Future** - Section hierarchy, chunking, retrieval

## Getting Help

- **API Docs**: http://localhost:8000/docs
- **README**: [backend/README.md](README.md)
- **Examples**: [backend/examples/ingestion_usage.py](examples/ingestion_usage.py)
- **Implementation Details**: [backend/IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

## Example Session

```bash
# Terminal 1: Start server
$ python backend/main.py
INFO: Started server process
INFO: Uvicorn running on http://0.0.0.0:8000

# Terminal 2: Test upload
$ curl -X POST "http://localhost:8000/upload/" \
  -F "file=@paper.pdf"
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "paper.pdf",
  "status": "completed",
  "page_count": 15,
  "processing_time_seconds": 8.5,
  "ocr_applied": false,
  "message": "Document processed successfully"
}

# Success! ✅
```

---

**Ready to process research papers! 🎉**
