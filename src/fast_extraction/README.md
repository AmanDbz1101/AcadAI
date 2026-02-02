# Fast Extraction Module

A high-performance document processing pipeline that uses **Docling** for rapid text extraction and **Groq LLM** for intelligent heading classification. Includes SQL-based deduplication to prevent redundant processing.

## Overview

This module provides a dual-path approach to document processing:

1. **Fast Path (Docling + Groq)**: Extract document structure and generate reading guides in 20-30 seconds
2. **Deduplication**: PDF hash-based caching prevents reprocessing the same document

### Key Features

- ✨ **Fast extraction**: Docling processes PDFs in 5-10 seconds
- 🤖 **Smart classification**: Groq LLM identifies paper title and meaningful sections
- 🔐 **Deduplication**: SHA256 hash-based document tracking
- 💾 **SQL database**: Persistent storage of document metadata
- 📖 **Auto guide generation**: Seamless integration with existing guide generation
- 📊 **Statistics tracking**: Document counts, element statistics, processing status

## Architecture

```
┌─────────────────┐
│   PDF Input     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Deduplication Check (SHA256)   │
│  ✓ Exists → Load cached         │
│  ✗ New → Process                │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│   Docling Fast Extraction       │
│   • Markdown output              │
│   • Heading hierarchy            │
│   • Element counts               │
│   • Page tracking                │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│   Groq LLM Classification       │
│   • Identify paper title         │
│   • Filter main sections         │
│   • Extract abstract             │
│   • Assign section levels        │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│   Groq LLM Inference            │
│   • Paper type classification    │
│   • Difficulty assessment        │
│   • Math-heavy detection         │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│   Simple Metadata Output        │
│   • Title, Abstract, Sections    │
│   • Global statistics            │
│   • Paper properties             │
└────────┬────────────────────────┘
         │
         ├──────────────────┐
         │                  │
         ▼                  ▼
┌──────────────┐   ┌──────────────────┐
│   Database   │   │  Guide Generation│
│   Storage    │   │  (3-pass guide)  │
└──────────────┘   └──────────────────┘
```

## Installation

```bash
# Install docling
pip install docling>=2.0.0

# Already installed dependencies
# - langchain-groq
# - pydantic>=2.0.0
# - python-dotenv
```

## Configuration

Set your Groq API key in `.env`:

```bash
GROQ_API_KEY=your_groq_api_key_here
```

## Usage

### Basic Usage

```python
from src.fast_extraction.pipeline import FastExtractionPipeline

# Initialize pipeline
pipeline = FastExtractionPipeline(
    db_path="fast_extraction_docs.db",
    output_dir="output"
)

# Process a PDF
document_id, metadata, is_cached = pipeline.process_document("paper.pdf")

print(f"Document ID: {document_id}")
print(f"Title: {metadata.paper_title}")
print(f"Sections: {len(metadata.sections)}")
print(f"Cached: {is_cached}")

# Generate reading guide
guide_path = pipeline.generate_guide(document_id)
print(f"Guide: {guide_path}")
```

### Command-Line Usage

```bash
# Process a paper
python test_fast_extraction.py path/to/paper.pdf

# The script will:
# 1. Check for duplicates
# 2. Extract metadata (if new)
# 3. Generate reading guide
# 4. Display statistics
```

### Deduplication Example

```python
# First run - processes document
doc_id_1, meta_1, cached_1 = pipeline.process_document("paper.pdf")
# cached_1 = False (newly processed)

# Second run - loads from cache
doc_id_2, meta_2, cached_2 = pipeline.process_document("paper.pdf")
# cached_2 = True (loaded from database)
# doc_id_1 == doc_id_2 (same document ID)
```

### Database Operations

```python
# Get document status
status = pipeline.get_document_status(document_id)
print(f"Status: {status['status']}")
print(f"Docling ready: {status['docling_ready']}")

# List all documents
docs = pipeline.list_documents(limit=10)
for doc in docs:
    print(f"{doc['document_id']}: {doc['title']}")

# Get statistics
stats = pipeline.get_statistics()
print(f"Total: {stats['total']}")
print(f"Docling ready: {stats['docling_ready']}")
```

## Module Structure

```
src/fast_extraction/
├── __init__.py                 # Module exports
├── models.py                   # Pydantic models
├── docling_extractor.py        # Fast markdown extraction
├── simple_metadata.py          # Groq-powered classification
├── dedup_database.py          # SQL deduplication layer
└── pipeline.py                 # Main orchestrator
```

### Component Details

#### 1. Docling Extractor (`docling_extractor.py`)

Fast PDF parsing using Docling library:
- **Markdown extraction**: Convert PDF to structured markdown
- **Heading detection**: Extract all section headers with levels
- **Element counting**: Track formulas, tables, figures, text blocks
- **Page tracking**: Associate elements with page numbers

#### 2. Simple Metadata Extractor (`simple_metadata.py`)

Groq LLM-powered classification:
- **Title identification**: Classify which heading is the paper title
- **Section filtering**: Exclude References, Acknowledgements, Appendix
- **Abstract extraction**: Locate and extract abstract text
- **Paper inference**: Classify paper type, difficulty, math content
- **Structured output**: JSON mode for reliable parsing

#### 3. Deduplication Database (`dedup_database.py`)

SQL-based document tracking:
- **SHA256 hashing**: Compute PDF file hash for deduplication
- **Status tracking**: PROCESSING → DOCLING_READY → API_COMPLETE
- **Metadata paths**: Store locations of generated JSON files
- **Query utilities**: Search, list, statistics

#### 4. Pipeline (`pipeline.py`)

Main orchestrator:
- **Duplicate detection**: Check hash before processing
- **Metadata extraction**: Coordinate Docling + Groq
- **Guide generation**: Integrate with existing guide system
- **Error handling**: Graceful failure with status updates

## Data Models

### DocumentStatus

```python
class DocumentStatus(str, Enum):
    PROCESSING = "processing"         # Currently extracting
    DOCLING_READY = "docling_ready"  # Fast extraction complete
    API_COMPLETE = "api_complete"     # Full API processing done
    FAILED = "failed"                 # Extraction failed
```

### SimpleMetadata

```python
class SimpleMetadata(BaseModel):
    document_id: str                  # UUID identifier
    paper_title: str                  # Classified title
    abstract: str                     # Extracted abstract
    sections: List[SectionInfo]       # Main content sections
    global_stats: GlobalStats         # Document-wide counts
    inference: PaperInference         # Paper classification
```

### SectionInfo

```python
class SectionInfo(BaseModel):
    original_name: str                # Section heading text
    level: int                        # 1-5 (section depth)
    page_start: int                   # Starting page number
    stats: SectionStats               # Element counts per section
```

## Database Schema

### documents Table

```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT UNIQUE NOT NULL,      -- UUID
    pdf_hash TEXT NOT NULL,                -- SHA256 hash
    title TEXT NOT NULL,                   -- Paper title
    status TEXT NOT NULL,                  -- DocumentStatus enum
    docling_metadata_path TEXT,            -- Path to metadata JSON
    api_metadata_path TEXT,                -- Path to full metadata (future)
    vectorstore_collection TEXT,           -- Qdrant collection name (future)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast lookups
CREATE INDEX idx_pdf_hash ON documents(pdf_hash);
CREATE INDEX idx_document_id ON documents(document_id);
CREATE INDEX idx_status ON documents(status);
```

## Output Files

### Metadata JSON (`{document_id}_docling_metadata.json`)

```json
{
  "document_id": "uuid-string",
  "paper_title": "Paper Title",
  "abstract": "Paper abstract text...",
  "sections": [
    {
      "original_name": "1. Introduction",
      "level": 1,
      "page_start": 1,
      "stats": {
        "formulas": 0,
        "tables": 0,
        "figures": 0,
        "text_blocks": 0
      }
    }
  ],
  "global_stats": {
    "total_formulas": 15,
    "total_tables": 3,
    "total_figures": 8,
    "total_text_blocks": 120,
    "total_pages": 12,
    "total_sections": 8
  },
  "inference": {
    "paper_type": "Empirical",
    "difficulty": "hard",
    "math_heavy": true
  }
}
```

### Guide JSON (`{document_id}_guide.json`)

Generated by the existing guide generation system. See [src/guide_generation/](../guide_generation/) for details.

## Performance

Typical timing for a 12-page research paper:

| Stage                    | Time    | Description                          |
|--------------------------|---------|--------------------------------------|
| PDF Hash                 | <1s     | SHA256 computation                   |
| Duplicate Check          | <1s     | Database query                       |
| Docling Extraction       | 5-10s   | Markdown + structure extraction      |
| Groq Classification      | 3-5s    | Heading classification (JSON mode)   |
| Groq Inference           | 2-3s    | Paper property inference             |
| Guide Generation         | 5-10s   | LLM-based guide creation             |
| **Total (first run)**    | **20-30s** | Full pipeline                     |
| **Total (cached)**       | **<2s** | Load from database                   |

## LLM Prompts

### Heading Classification Prompt

Instructs Groq to:
1. Identify the paper title from headings list
2. Extract abstract text
3. Filter main content sections only
4. Exclude: References, Acknowledgements, Appendix, Funding, etc.
5. Return structured JSON with `title`, `abstract`, `sections[]`

### Paper Inference Prompt

Instructs Groq to classify:
1. **paper_type**: Survey, System, Theoretical, Empirical, etc.
2. **difficulty**: easy, medium, hard
3. **math_heavy**: true/false based on content

Both prompts use **JSON mode** for reliable structured output.

## Error Handling

The pipeline handles errors gracefully:

```python
try:
    # Extraction process
    metadata = extractor.extract_metadata(pdf_path, document_id)
except Exception as e:
    # Mark as failed in database
    db.update_status(document_id, DocumentStatus.FAILED)
    raise RuntimeError(f"Extraction failed: {e}")
```

Failed documents are marked in the database and can be retried with `force_reprocess=True`.

## Future Enhancements

1. **Unstructured API Integration**: High-quality parsing in background
2. **Vectorstore Integration**: Auto-populate Qdrant collections
3. **Section-level Statistics**: Per-section formula/table/figure counts
4. **Batch Processing**: Process multiple PDFs efficiently
5. **API Endpoints**: FastAPI integration for web service
6. **Progress Tracking**: WebSocket updates for long-running tasks

## Integration with Existing System

### Metadata Extraction

This module complements the existing metadata extraction pipelines:

- **PDF-based pipeline** (`src/metadata_extraction/src/`): More detailed, slower
- **Qdrant-based pipeline** (`src/metadata_extraction/api_src/`): Includes element stats
- **Fast extraction pipeline** (this module): Fastest, good enough for guides

### Guide Generation

Seamlessly integrates with existing guide generation:

```python
from src.guide_generation.minimal_guide_generation import generate_minimal_guide_llm

# Fast extraction provides the required metadata format
guide = generate_minimal_guide_llm(
    metadata_path="output/{document_id}_docling_metadata.json",
    output_path="output/{document_id}_guide.json"
)
```

## Troubleshooting

### "Module 'docling' not found"

```bash
pip install docling>=2.0.0
```

### "Groq API key not found"

Add to `.env`:
```bash
GROQ_API_KEY=your_key_here
```

### "KeyError: 'stats'"

Ensure `SectionInfo` model includes `stats` field with default:
```python
stats: SectionStats = Field(default_factory=SectionStats)
```

### Database locked

Close all connections or delete `fast_extraction_docs.db` and reprocess.

## Examples

See [test_fast_extraction.py](../../test_fast_extraction.py) for a complete working example.

## License

Part of the Research Paper Assistant project.
