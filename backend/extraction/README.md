# Extraction Module

**Person 1's Workspace** - PDF Processing, Metadata Extraction, Section Hierarchy

## Overview

The extraction module handles the complete pipeline from PDF file to structured document with metadata and section hierarchy.

## Workflow

```
PDF File
   ↓
[Validation] → Check file integrity, format, size
   ↓
[PDF Loading] → Extract text with Docling, preserve layout
   ↓
[OCR (if needed)] → Process scanned/low-quality PDFs
   ↓
[Metadata Extraction] → Extract title, abstract, authors, sections
   ↓
[Hierarchy Detection] → Build section tree with proper nesting
   ↓
ProcessedDocument + SectionHierarchy
```

## Directory Structure

```
extraction/
├── api/routes/
│   └── extraction.py          # API endpoints for upload & processing
├── app/
│   ├── validation.py          # PDF validation logic
│   ├── pdf_loader.py          # Docling-based text extraction
│   ├── ocr.py                 # OCR handler for scanned PDFs
│   ├── metadata_extractor.py # Metadata extraction (Docling + Groq)
│   ├── groq_fallback.py       # LLM fallback for missing fields
│   └── section_detector.py    # Section hierarchy detection
├── models/
│   ├── document.py            # ValidatedDocument, PageContent
│   ├── metadata.py            # ExtractedMetadata, ProcessedDocument
│   └── section_hierarchy.py  # SectionNode, SectionHierarchy
├── pipelines/
│   ├── ingest_pipeline.py     # Orchestrates validation → loading → OCR
│   ├── metadata_pipeline.py   # Orchestrates metadata extraction
│   └── section_hierarchy_pipeline.py  # Orchestrates hierarchy detection
├── services/
│   ├── extraction_service.py  # High-level unified service
│   └── ingestion_service.py   # Legacy ingestion service
└── examples/
    └── simple_extraction.py   # Usage examples
```

## Quick Start

### Using the Extraction Service (Recommended)

```python
from pathlib import Path
from backend.extraction.services.extraction_service import ExtractionService

# Initialize service
service = ExtractionService(enable_ocr=True)

# Process a PDF
result = service.process_pdf(
    pdf_path=Path("paper.pdf"),
    extract_hierarchy=True
)

# Access results
validated_doc = result["validated_doc"]      # Raw extraction
processed_doc = result["processed_doc"]      # With metadata
hierarchy = result["hierarchy"]              # Section tree

print(f"Title: {processed_doc.metadata.title}")
print(f"Sections: {hierarchy.total_sections}")
```

### Using Individual Pipelines

```python
from backend.extraction.pipelines.ingest_pipeline import IngestPipeline
from backend.extraction.pipelines.metadata_pipeline import MetadataExtractionPipeline
from backend.extraction.pipelines.section_hierarchy_pipeline import SectionHierarchyPipeline

# Step 1: Ingest
ingest = IngestPipeline()
validated_doc = ingest.ingest(Path("paper.pdf"))

# Step 2: Extract metadata
metadata = MetadataExtractionPipeline()
processed_doc = metadata.extract(validated_doc)

# Step 3: Detect hierarchy
hierarchy_pipeline = SectionHierarchyPipeline()
hierarchy_result = hierarchy_pipeline.detect(processed_doc)
```

## API Endpoints

### Upload & Process PDF
```bash
POST /extraction/upload
```
Upload a PDF file and process it through the full pipeline.

### Process from Path
```bash
POST /extraction/process
Body: {"pdf_path": "/path/to/paper.pdf", "extract_hierarchy": true}
```

### Health Check
```bash
GET /extraction/health
```

## Key Features

### 1. PDF Validation
- File integrity checks
- Format validation
- Page count verification
- Encryption detection

### 2. Text Extraction (Docling)
- Fast extraction (5-10s per paper)
- Layout signal preservation
- Reading order detection
- Table, figure, formula tracking

### 3. Adaptive OCR
- Automatic machine-readability detection
- Selective page-level OCR
- Confidence scoring
- Layout preservation

### 4. Metadata Extraction
- Docling structure analysis
- Groq LLM classification
- Extracts: title, abstract, authors, sections
- Global statistics and paper type inference

### 5. Section Hierarchy
- Typography-based detection
- Numbering pattern recognition
- Keyword matching
- Navigable tree structure

## Working on Extraction Tasks

### Testing Your Changes

```bash
# Run extraction tests
cd backend
pytest extraction/tests/ -v

# Test with a single PDF
python extraction/examples/simple_extraction.py
```

### Common Tasks

**Add new metadata field:**
1. Update `models/metadata.py` - add field to `ExtractedMetadata`
2. Update `app/metadata_extractor.py` - add extraction logic
3. Update tests

**Improve section detection:**
1. Modify `app/section_detector.py` - adjust detection rules
2. Test with various paper formats
3. Update `pipelines/section_hierarchy_pipeline.py` if needed

**Add new validation:**
1. Update `app/validation.py` - add validation logic
2. Update `pipelines/ingest_pipeline.py` - integrate validation

## Configuration

All configuration is in `backend/shared/config/settings.py`:

```python
ENABLE_OCR: bool = True              # Enable OCR processing
OCR_MIN_TEXT_DENSITY: float = 50.0  # Chars/page threshold
EXTRACTION_TIMEOUT: int = 120        # Seconds
GROQ_API_KEY: str                    # For metadata extraction
```

## Dependencies

- `docling` - PDF extraction and structure analysis
- `docling-core` - Data models
- `groq` - LLM API for metadata extraction
- Standard PDF libraries

## Next Steps

After extraction, documents can be passed to the **RAG module** for:
- Chunking
- Embedding generation
- Vector store indexing
- Retrieval

See `../rag/README.md` for details.
