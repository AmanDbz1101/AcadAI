# Metadata Extraction Module

## Overview
The metadata extraction module extends the PDF ingestion pipeline to extract structured bibliographic metadata from research papers. It combines heuristic extraction with LLM-based fallback for robust metadata extraction.

## Features

### 1. **Heuristic Extraction**
- Uses Docling layout analysis and pattern matching
- Extracts key metadata fields:
  - Title (largest text on first page)
  - Authors (text below title, name patterns)
  - Abstract (keyword-based section detection)
  - Keywords (section detection and parsing)
  - DOI (pattern matching)
  - Affiliations (keyword-based detection)

### 2. **LLM Fallback**
- Uses Groq API with LLaMA-3.3-70B Versatile model
- Activated when heuristic confidence is low (<60% by default)
- Extracts missing fields using structured prompts
- Returns JSON-formatted results

### 3. **Integrated Pipeline**
- Seamlessly integrates with PDF ingestion module
- Single API call for complete processing: PDF → ValidatedDocument → ProcessedDocument
- Supports batch processing

### 4. **API Endpoints**
- `POST /process/` - Process single PDF
- `POST /process/batch` - Process multiple PDFs
- `GET /process/health` - Health check

## Architecture

```
PDF File
   ↓
[PDF Ingestion Pipeline]
   ↓
ValidatedDocument
   ↓
[Metadata Extraction Pipeline]
   ├─→ Heuristic Extractor
   │     ↓
   │   ExtractedMetadata (confidence check)
   │     ↓
   └─→ [If confidence < threshold]
         ↓
       Groq LLM Fallback
         ↓
       Merge Results
         ↓
ProcessedDocument
```

## Installation

1. **Install dependencies:**
```bash
cd backend
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

3. **Required environment variables:**
```bash
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
ENABLE_LLM_FALLBACK=true
LLM_FALLBACK_THRESHOLD=0.6
```

## Usage

### Command Line

**Single document:**
```python
from backend.services.processing_service import IntegratedPipeline

pipeline = IntegratedPipeline()
validated_doc, processed_doc = pipeline.ingest_and_process("paper.pdf")

print(f"Title: {processed_doc.metadata.title}")
print(f"Authors: {[a.name for a in processed_doc.metadata.authors]}")
print(f"Confidence: {processed_doc.metadata.confidence_score:.2%}")
```

**Batch processing:**
```python
results = pipeline.process_batch([
    "paper1.pdf",
    "paper2.pdf",
    "paper3.pdf"
])

for validated, processed in results:
    print(f"{processed.metadata.title}: {processed.metadata.get_field_coverage():.0%}")
```

### API

**Start server:**
```bash
cd backend
python -m backend.api.app
```

**Process single PDF:**
```bash
curl -X POST "http://localhost:8000/process/" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_path": "/path/to/paper.pdf",
    "use_fallback": true
  }'
```

**Process batch:**
```bash
curl -X POST "http://localhost:8000/process/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_paths": ["/path/to/paper1.pdf", "/path/to/paper2.pdf"],
    "use_fallback": true,
    "continue_on_error": true
  }'
```

### Testing

**Run performance test:**
```bash
python test_metadata_extraction.py
```

This will:
- Process all PDFs in `Research Papers/` and `input/` folders
- Extract metadata using the complete pipeline
- Generate performance report with:
  - Success rate
  - Processing time statistics
  - Field extraction rates
  - Fallback usage statistics
  - Detailed results for each document

**Output:**
```
📊 Summary:
  Total Documents: 14
  Successful: 13
  Failed: 1
  Success Rate: 92.9%

⏱️  Performance:
  Average Time: 6.8s
  
📝 Metadata Extraction:
  Average Field Coverage: 78.5%
  Fallback Usage Rate: 42.9%
  
🎯 Field Extraction Rates:
  Title: 92.3%
  Authors: 84.6%
  Abstract: 76.9%
  Keywords: 61.5%
  DOI: 53.8%
```

## Models

### ExtractedMetadata
```python
{
    "title": "Paper Title",
    "authors": [
        {"name": "John Doe", "email": "john@example.com", "affiliation": "University"}
    ],
    "abstract": "Paper abstract text...",
    "keywords": ["keyword1", "keyword2"],
    "doi": "10.1234/example",
    "publication_venue": "Conference/Journal Name",
    "publication_year": 2024,
    "extraction_method": "heuristic+llm",
    "fallback_used": true,
    "confidence_score": 0.85,
    "missing_fields": []
}
```

### ProcessedDocument
```python
{
    "document_id": "uuid",
    "metadata": ExtractedMetadata,
    "processing_time_seconds": 8.5,
    "sections": [],  # For future modules
    "extracted_elements": []  # For future modules
}
```

## Configuration

### Heuristic Extractor
```python
MetadataExtractor(
    title_min_font_size=14.0,
    abstract_keywords=["abstract"],
    keywords_keywords=["keywords", "key words"]
)
```

### Groq Fallback
```python
GroqFallbackExtractor(
    api_key="your_key",
    model="llama-3.3-70b-versatile",
    max_tokens=2048,
    temperature=0.1
)
```

### Pipeline
```python
MetadataExtractionPipeline(
    use_fallback=True,
    fallback_threshold=0.6  # Use fallback if confidence < 60%
)
```

## Performance

**Typical metrics:**
- Processing time: 6-8 seconds per document (with fallback)
- Heuristic-only: 1-2 seconds per document
- Field coverage: 70-85% average
- Success rate: 90%+

**Optimization tips:**
1. Adjust `fallback_threshold` based on accuracy requirements
2. Use batch processing for multiple documents
3. Cache Groq API responses for repeated queries
4. Fine-tune heuristic rules for specific document types

## Error Handling

The pipeline handles common errors gracefully:
- Missing PDF files
- Corrupted PDFs
- API timeouts
- Invalid metadata formats

All errors are logged with detailed context for debugging.

## Integration with Other Modules

The metadata extraction module outputs `ProcessedDocument` objects that can be consumed by:
1. **Section Hierarchy Detection** - Use extracted metadata and document structure
2. **Section-Aware Chunking** - Combine with section detection for intelligent chunking
3. **Embedding Generation** - Enrich chunks with metadata context
4. **Database Storage** - Store metadata for retrieval and analysis

## Future Enhancements

1. **Multi-language support** - Extend heuristics for non-English papers
2. **Custom field extraction** - Allow users to define custom metadata fields
3. **Citation extraction** - Extract and parse references
4. **Author disambiguation** - Link authors across papers
5. **Venue normalization** - Standardize conference/journal names

## License
Part of Research Paper Assistant project.
