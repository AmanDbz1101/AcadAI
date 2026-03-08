# Research Paper Assistant - Backend v3.0

**Modular backend for research paper processing and retrieval**

## 🎯 Overview

The backend is organized into **two focused modules** for parallel development:

1. **Extraction Module** (Person 1) - PDF → Text → Metadata → Hierarchy
2. **RAG Module** (Person 2) - Chunking → Embeddings → Vectorstore → Retrieval

## 📦 Module Structure

```
backend/
├── extraction/              # Person 1's workspace
│   ├── api/routes/         # Extraction endpoints
│   ├── app/                # PDF loading, metadata, hierarchy
│   ├── models/             # Document data models
│   ├── pipelines/          # Orchestration workflows
│   ├── services/           # High-level extraction service
│   └── README.md           # Extraction documentation
│
├── rag/                    # Person 2's workspace
│   ├── api/routes/         # RAG endpoints
│   ├── app/                # Vectorstore, embeddings
│   ├── models/             # Chunking & guide models
│   ├── pipelines/          # Chunking & guide generation
│   ├── services/           # High-level RAG service
│   └── README.md           # RAG documentation
│
├── shared/                 # Common infrastructure
│   ├── config/             # Settings
│   └── utils/              # Logging, paths
│
└── api/                    # Main API entry point
    └── app.py              # Routes to extraction + rag
```

## 🔄 Complete Workflow

```
PDF File
   ↓
┌─────────────────────────────────┐
│   EXTRACTION MODULE (Person 1)  │
├─────────────────────────────────┤
│ 1. Validation                   │
│ 2. Text Extraction (Docling)    │
│ 3. OCR (if needed)              │
│ 4. Metadata Extraction          │
│ 5. Section Hierarchy Detection  │
└──────────────┬──────────────────┘
               ↓
    ProcessedDocument + Hierarchy
               ↓
┌─────────────────────────────────┐
│      RAG MODULE (Person 2)       │
├─────────────────────────────────┤
│ 1. Section-Aware Chunking       │
│ 2. Embedding Generation         │
│ 3. Vector Store Indexing        │
│ 4. Retrieval                    │
└──────────────┬──────────────────┘
               ↓
         Search Results
```

## 🏗️ Features by Module

### Extraction Module ✅

- **PDF Validation**: File integrity, format, encryption checks
- **Text Extraction**: Docling-based extraction with layout preservation
- **Adaptive OCR**: Selective OCR for scanned PDFs
- **Metadata Extraction**: Title, abstract, authors, sections (Docling + Groq LLM)
- **Section Hierarchy**: Typography-based hierarchical structure detection

[→ Full Extraction Documentation](extraction/README.md)

### RAG Module ✅

- **Section-Aware Chunking**: Respects document structure
- **Hybrid Embeddings**: SPECTER2 (dense) + BM25 (sparse)
- **Vector Store**: Qdrant integration for persistent storage
- **Semantic Retrieval**: Similarity search with metadata filtering
- **Reading Guides**: Three-pass reading strategy generation

[→ Full RAG Documentation](rag/README.md)

## 🚀 Quick Start

### Installation

```bash
# Navigate to project root
cd "Research Paper Assistant"

# Activate virtual environment
source env_research/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
```

### Running the API

```bash
# Start the unified API server
uvicorn backend.api.app:app --reload --host 0.0.0.0 --port 8000
```

### API Endpoints

**Extraction Endpoints:**
```bash
# Upload and process a PDF
curl -X POST "http://localhost:8000/extraction/upload" \
  -F "file=@paper.pdf" \
  -F "extract_hierarchy=true"

# Process from file path
curl -X POST "http://localhost:8000/extraction/process" \
  -H "Content-Type: application/json" \
  -d '{"pdf_path": "/path/to/paper.pdf", "extract_hierarchy": true}'

# Health check
curl http://localhost:8000/extraction/health
```

**RAG Endpoints:**
```bash
# Retrieve relevant chunks
curl -X POST "http://localhost:8000/rag/retrieve" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the main contribution?",
    "top_k": 5
  }'

# Health check
curl http://localhost:8000/rag/health
```

**API Documentation:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## � Developer Guide

### Working on Extraction (Person 1)

Your workspace: `backend/extraction/`

**What you work on:**
- PDF validation and loading
- Text extraction improvements
- Metadata extraction accuracy
- Section hierarchy detection
- OCR quality

**Quick test:**
```bash
# Test extraction service
python -c "from backend.extraction.services.extraction_service import ExtractionService; print('✓ Extraction OK')"

# Process a test PDF
python backend/extraction/examples/simple_extraction.py
```

**Common tasks:**
- Improve metadata extraction: Edit `extraction/app/metadata_extractor.py`
- Enhance hierarchy detection: Edit `extraction/app/section_detector.py`
- Add validation rules: Edit `extraction/app/validation.py`

[→ Full Extraction Guide](extraction/README.md)

### Working on RAG (Person 2)

Your workspace: `backend/rag/`

**What you work on:**
- Chunking strategies
- Embedding generation
- Vector store integration
- Retrieval quality
- Reading guide generation

**Quick test:**
```bash
# Test RAG service
python -c "from backend.rag.services.rag_service import RAGService; print('✓ RAG OK')"

# Test chunking
python -c "from backend.rag.pipelines.chunking_pipeline import ChunkingPipeline; print('✓ Chunking OK')"
```

**Common tasks:**
- Adjust chunking: Edit `rag/pipelines/chunking_pipeline.py`
- Improve embeddings: Edit `rag/app/embeddings.py`
- Enhance retrieval: Edit `rag/services/rag_service.py`

[→ Full RAG Guide](rag/README.md)

### Module Independence

**Both developers can work simultaneously:**
- Extraction produces `ProcessedDocument` + `SectionHierarchy`
- RAG consumes these as inputs
- Clear interface between modules via data models

**Shared components:**
- Configuration: `backend/shared/config/settings.py`
- Utilities: `backend/shared/utils/`

## �📊 Data Models

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
