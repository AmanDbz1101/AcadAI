# Metadata Extraction Module - Quickstart Guide

## Quick Setup (5 minutes)

### 1. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Groq API (Optional but Recommended)
```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your Groq API key
# Get a free API key from: https://console.groq.com/
echo "GROQ_API_KEY=your_actual_groq_api_key" >> .env
```

**Note**: Without Groq API key, the extractor will still work using Docling structure analysis only, but LLM classification features (paper type inference, difficulty assessment) will be disabled.

### 3. Test the Pipeline

**Option A: Run the example script**
```bash
cd ..  # Go back to project root
python example_metadata_extraction.py
```

This will process sample PDFs and show extracted metadata.

**Option B: Quick Python test**
```python
from backend.services.processing_service import IntegratedPipeline

# Initialize pipeline
pipeline = IntegratedPipeline()

# Process a single PDF
validated_doc, processed_doc = pipeline.ingest_and_process("input/sample_1.pdf")

# View results
metadata = processed_doc.metadata
print(f"Title: {metadata.title}")
print(f"Abstract: {metadata.abstract[:200] if metadata.abstract else 'Not found'}...")
print(f"Sections: {len(metadata.sections)}")
print(f"Total Pages: {metadata.global_stats.total_pages if metadata.global_stats else 'N/A'}")
print(f"Confidence: {metadata.confidence_score:.1%}")
```

### 4. Start the API Server
```bash
cd backend
python -m backend.api.app
```

Visit http://localhost:8000/docs for interactive API documentation.

## Example API Calls

### Process Single PDF
```bash
curl -X POST "http://localhost:8000/process/" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_path": "input/sample_1.pdf"
  }'
```

### Process Multiple PDFs
```bash
curl -X POST "http://localhost:8000/process/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_paths": [
      "input/sample_1.pdf",
      "input/sample_2.pdf"
    ],
    "continue_on_error": true
  }'
```

## Understanding the Output

The pipeline returns a `ProcessedDocument` with extracted metadata:

```json
{
  "document_id": "uuid-here",
  "metadata": {
    "title": "Research Paper Title",
    "abstract": "Paper abstract text...",
    "sections": [
      {
        "original_name": "Introduction",
        "level": 1,
        "page_start": 1
      },
      {
        "original_name": "Methods",
        "level": 1,
        "page_start": 3
      }
    ],
    "global_stats": {
      "total_pages": 10,
      "total_sections": 5,
      "total_formulas": 15,
      "total_tables": 3,
      "total_figures": 8
    },
    "inference": {
      "paper_type": "research_article",
      "difficulty": "advanced",
      "math_heavy": true
    },
    "extraction_method": "docling",
    "fallback_used": false,
    "confidence_score": 0.85,
    "missing_fields": [],
    "field_coverage": 1.0
  },
  "processing_time_seconds": 4.2
}
```

## Key Metrics

- **confidence_score**: 0.0-1.0, indicates extraction confidence
- **field_coverage**: Percentage of core fields extracted (title, abstract, sections)
- **fallback_used**: Whether pattern matching fallback was needed
- **missing_fields**: List of fields that couldn't be extracted

## Extraction Approach

The module uses a two-stage approach:

1. **Docling Structure Extraction**: Extracts document structure, headings, and elements
2. **Groq LLM Classification** (optional): Classifies heading types and provides paper inference

### Without Groq API Key
- Extracts title, abstract, and sections using Docling layout analysis
- Uses pattern matching for abstract detection
- No LLM-based inference (paper_type, difficulty, math_heavy will be basic values)

### With Groq API Key
- Same as above, plus:
- LLM-based heading classification (Introduction, Methods, Results, etc.)
- Paper type inference (research_article, review, survey, etc.)
- Difficulty assessment (beginner, intermediate, advanced)
- Math-heavy detection

## Customization

### Extract from Different Sources
```python
from backend.services.processing_service import ProcessingService

# Initialize service
service = ProcessingService()

# Process single document
result = service.process_document("path/to/paper.pdf")

# Access metadata
metadata = result.metadata
print(f"Title: {metadata.title}")
print(f"Sections: {[(s.original_name, s.level) for s in metadata.sections]}")
```

## Troubleshooting

### No metadata extracted
- Check if PDF is text-based (not scanned image)
- Verify PDF follows standard academic format
- Enable OCR in backend/config/settings.py if needed

### LLM features not working
- Verify `GROQ_API_KEY` is set in `.env`
- Check Groq API status and rate limits
- Review logs for API errors
- System will gracefully fall back to structure-only extraction

### Slow processing
- Typical processing time: 2-5s per document
- With LLM classification: +1-2s per document
- Use batch processing for multiple documents

## Next Steps

1. **Integrate with your workflow** - Use the `IntegratedPipeline` in your application
2. **Customize extraction** - Modify `MetadataExtractor` for your document types
3. **Add more fields** - Extend the models and extraction logic
4. **Build on top** - Use extracted sections for hierarchy detection (Module 3)

## Support

For issues or questions:
1. Check the implementation summary: `backend/IMPLEMENTATION_SUMMARY.md`
2. Review logs in `logs/`
3. Check API documentation at `/docs`
