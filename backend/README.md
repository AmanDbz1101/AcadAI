# Research Paper Assistant - Backend v2.0

Production-grade backend for processing research papers with PDF ingestion, text extraction, and intelligent retrieval.

## 📋 Module 1: PDF Ingestion (Completed)

The PDF Ingestion module provides reliable PDF processing with:

### Features

✅ **Comprehensive Validation**
- File integrity checks (corruption detection)
- Size and format validation
- Page count verification
- Encryption detection

✅ **Intelligent Text Extraction**
- Docling-powered extraction (5-10s per paper)
- Layout signal preservation (bounding boxes, fonts)
- Reading order detection
- Table, figure, and formula tracking

✅ **Adaptive OCR**
- Automatic machine-readability detection
- Selective OCR for low-density pages
- Confidence scoring
- Layout preservation during OCR

✅ **Production-Ready API**
- FastAPI with async support
- File upload handling
- Hash-based deduplication
- Comprehensive error handling
- Progress tracking support

## 🏗️ Architecture

```
backend/
├── api/                  # FastAPI application
│   ├── routes/
│   │   └── upload.py    # Upload endpoint
│   └── app.py           # Main FastAPI app
├── app/
│   └── ingestion/       # Ingestion logic
│       ├── validation.py    # PDF validation
│       ├── pdf_loader.py    # Docling integration
│       └── ocr.py          # OCR handler
├── models/
│   └── document.py      # Data models
├── pipelines/
│   └── ingest_pipeline.py   # Orchestration
├── services/
│   └── ingestion_service.py # High-level API
├── config/
│   └── settings.py      # Configuration
└── main.py              # Entry point
```

## 🚀 Quick Start

### Installation

```bash
# Install dependencies (assuming requirements.txt includes needed packages)
pip install -r requirements.txt

# Or install specific packages
pip install fastapi uvicorn pydantic pydantic-settings
pip install pymupdf docling docling-core
```

### Running the API

```bash
# Start the server
python backend/main.py

# Or use uvicorn directly
uvicorn backend.api.app:app --reload --host 0.0.0.0 --port 8000
```

### API Endpoints

**Upload PDF:**
```bash
curl -X POST "http://localhost:8000/upload/" \
  -F "file=@paper.pdf" \
  -F "force_ocr=false"
```

**Health Check:**
```bash
curl http://localhost:8000/upload/health
```

**API Documentation:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 📊 Data Models

### ValidatedDocument

The core output from ingestion:

```python
ValidatedDocument(
    document_id: UUID          # Unique identifier
    pdf_path: Path            # Original PDF location
    pdf_hash: str             # SHA256 for deduplication
    pages: List[PageContent]  # Page-wise content
    full_text: str            # Concatenated text
    page_count: int           # Number of pages
    ocr_metadata: OCRMetadata # OCR information
    status: DocumentStatus    # Processing status
    processing_time_seconds: float
)
```

### PageContent

Per-page information:

```python
PageContent(
    page_number: int
    text: str
    layout_signals: LayoutSignals  # Bounding boxes, fonts
    word_count: int
    has_images: bool
    has_tables: bool
    has_formulas: bool
)
```

## ⚙️ Configuration

Environment variables (or `.env` file):

```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=false

# Upload Configuration
UPLOAD_DIR=uploads
MAX_FILE_SIZE_MB=50
EXTRACTION_TIMEOUT=120

# OCR Configuration
ENABLE_OCR=true
OCR_MIN_TEXT_DENSITY=50.0

# Caching
ENABLE_CACHE=false
CACHE_DIR=cache

# Logging
LOG_LEVEL=INFO
LOG_DIR=logs
```

## 🔧 Programmatic Usage

### Direct Pipeline Usage

```python
from pathlib import Path
from backend.pipelines import IngestPipeline

# Initialize pipeline
pipeline = IngestPipeline()

# Process a PDF
document = pipeline.process(
    pdf_path=Path("paper.pdf"),
    force_ocr=False
)

print(f"Processed: {document.page_count} pages")
print(f"Text length: {len(document.full_text)} chars")
print(f"OCR used: {document.ocr_metadata.was_ocr_applied}")
```

### Using the Service Layer

```python
from pathlib import Path
from backend.services import IngestionService

# Initialize service with caching
service = IngestionService(
    cache_dir=Path("cache"),
    enable_deduplication=True
)

# Ingest with progress callback
def progress(message, pct):
    print(f"[{pct:.0f}%] {message}")

document = service.ingest(
    pdf_path=Path("paper.pdf"),
    progress_callback=progress
)
```

### Batch Processing

```python
from pathlib import Path
from backend.pipelines import IngestPipeline

pipeline = IngestPipeline()

pdf_files = list(Path("papers/").glob("*.pdf"))

results = pipeline.process_batch(
    pdf_paths=pdf_files,
    continue_on_error=True
)

print(f"Successful: {len(results['successful'])}")
print(f"Failed: {len(results['failed'])}")
```

## 🧪 Testing

### Manual Testing

```python
# Test validation only
from backend.app.ingestion import PDFValidator

validator = PDFValidator(max_file_size_mb=50)
result = validator.validate(Path("paper.pdf"))

if result.is_valid:
    print(f"Valid PDF: {result.page_count} pages")
else:
    for error in result.errors:
        print(f"Error: {error.message}")
```

### OCR Testing

```python
# Test OCR detection
from backend.app.ingestion import PDFLoader

loader = PDFLoader()
result = loader.load(Path("paper.pdf"))

readability = loader.detect_readability(result['pages'])
print(f"Machine readable: {readability['is_machine_readable']}")
print(f"Recommendation: {readability['recommendation']}")
```

## 📈 Performance

**Typical Processing Times:**
- Digital PDF (no OCR): 5-10 seconds
- Scanned PDF (with OCR): 15-30 seconds
- Large PDF (100+ pages): 30-60 seconds

**Resource Usage:**
- Memory: ~200-500MB per document
- CPU: Single-threaded (docling limitation)

## 🔍 Troubleshooting

### Common Issues

**Import Errors:**
```bash
# Ensure backend is in Python path
export PYTHONPATH="${PYTHONPATH}:/path/to/Research Paper Assistant"
```

**Docling Not Found:**
```bash
pip install docling docling-core
```

**PyMuPDF Errors:**
```bash
pip install pymupdf
```

**Pydantic v2 Required:**
```bash
pip install "pydantic>=2.0"
```

## 🗺️ Next Steps

### Module 2: Document Processing (Coming Next)
- Layout analysis
- Metadata extraction
- Formula/table/figure extraction

### Module 3: Section Hierarchy Detection
- Section header detection
- Hierarchy building
- Section normalization

### Module 4: Section-Aware Chunking
- Semantic chunking
- Section boundary preservation
- Metadata attachment

## 📝 API Response Examples

**Successful Upload:**
```json
{
  "document_id": "123e4567-e89b-12d3-a456-426614174000",
  "filename": "paper.pdf",
  "status": "completed",
  "page_count": 15,
  "processing_time_seconds": 8.5,
  "ocr_applied": false,
  "message": "Document processed successfully"
}
```

**Validation Error:**
```json
{
  "error": "VALIDATION_FAILED",
  "message": "PDF validation failed: FILE_TOO_LARGE",
  "details": "Size: 75.2MB, Limit: 50MB"
}
```

## 🤝 Contributing

This is Module 1 of the complete system. See `plans/1_complete_plan.md` for the full roadmap.

## 📄 License

Research Paper Assistant Backend v2.0
