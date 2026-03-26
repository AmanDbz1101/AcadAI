# Backend

Simplified backend structure for Research Paper Assistant.

## Structure

```
backend/
├── extraction/          # PDF extraction module
│   ├── extraction.py           # Main extraction script
│   ├── streamlit_extraction.py # Streamlit UI for extraction
│   ├── pipelines/              # Core extraction pipelines
│   ├── models/                 # Data models
│   └── app/                    # Core extraction components
│
└── rag/                # Reading guide generation module
    ├── rag.py                  # Main guide generation script
    ├── streamlit_rag.py        # Streamlit UI for guide generation
    ├── pipelines/              # Core RAG pipelines
    └── models/                 # Data models
```

## Quick Start

### 1. Extraction

Extract metadata, hierarchy, and full text from PDF:

**Command line:**
```bash
cd backend/extraction
python extraction.py path/to/paper.pdf
```

**Streamlit UI:**
```bash
cd backend/extraction
streamlit run streamlit_extraction.py
```

Output files saved to `input/` folder:
- `{doc_id}_metadata.json` - Extracted metadata
- `{doc_id}_hierarchy.json` - Section hierarchy
- `{doc_id}_fulltext.txt` - Full document text
- `{doc_id}_complete.json` - Complete processed document

### 2. Guide Generation

Generate three-pass reading guide from metadata:

**Command line:**
```bash
cd backend/rag
python rag.py input/{doc_id}_complete.json
```

**Streamlit UI:**
```bash
cd backend/rag
streamlit run streamlit_rag.py
```

Output files saved to `output/` folder:
- `{doc_id}_guide.json` - Generated reading guide
- `{doc_id}_guide_result.json` - Generation metadata

## Requirements

Make sure to set your Groq API key:
```bash
export GROQ_API_KEY="your-api-key-here"
```

Or provide it when using the Streamlit UIs.

## Features

### Extraction Module
- PDF validation and text extraction
- Adaptive OCR for scanned documents
- Metadata extraction (title, abstract, sections)
- Section hierarchy detection
- Formula, table, and figure detection
- Saves all data to `input/` folder

### RAG Module
- Three-pass reading guide generation
- Based on metadata and section hierarchy only
- Structured steps with retrieval hints
- LLM-powered guide creation using Groq
- Saves guides to `output/` folder

## Notes

- Both modules use Streamlit for easy interaction
- All FastAPI code has been removed for simplicity
- Pipelines and models are organized in subfolders
- Input/output folders are at the project root level

## Deferred Answer Generation

Backend now supports deferred one-question answer generation.

Integration guide:
- See ../docs/DEFERRED_ANSWER_API.md for endpoints and UI wiring contract.
