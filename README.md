<div align="center">
  # ResearchAgent — Research Paper Assistant

  [![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-%3E=0.104.0-green.svg)](https://fastapi.tiangolo.com/)
  [![React](https://img.shields.io/badge/React-18.x-blue.svg)](https://reactjs.org/)
</div>

---

## 📌 What this project is

ResearchAgent (a.k.a. Research Paper Assistant) is an end-to-end system for ingesting research PDFs, extracting structured artifacts (metadata, sections, tables, figures, formulas), persisting them to PostgreSQL, indexing for retrieval, and serving them via a FastAPI read API and a React frontend. It also provides LangGraph-based analysis workflows (categorization, guide generation, retrieve-and-QA) and a technical-term detection subsystem.

---

## 📋 Table of Contents
- [Problem Statement](#-problem-statement)
- [Solution & Features](#-solution--features)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Setup & Quickstart](#-setup--quickstart)
- [Usage](#-usage)
- [Technology Stack](#-technology-stack)
- [Developer Notes](#-developer-notes)
- [Testing](#-testing)
- [Contributing & License](#-contributing--license)

---

## 🎯 Problem Statement

Despite the growing importance of research literacy, many students and early-stage researchers struggle to read and comprehend academic papers effectively. Traditional read-
1ing methods and existing AI tools fail to guide beginners through complex language, dense technical content, and varied paper structures. Specific limitations include the absence of paper-type-aware reading guidance, global retrieval that returns chunks from irrelevant sections, inability to process tables and figures as semantically meaningful units, and no structured mechanism for section-specific comprehension assessment. These gaps highlight the need for an intelligent system that can classify papers, structure their content by type, and provide grounded, section-scoped question answering to support compre-
hension.

---

## 💡 Solution & Features

AcadAI addresses a genuine gap in the tooling available to students and researchers approaching unfamiliar academic literature. By combining paper type classification,
content-type-aware chunking, and section-scoped retrieval, the system reduces the cognitive effort required to navigate a research paper and provides structured, grounded guid-
ance at the point of reading. For undergraduate students undertaking a first literature review, or early-stage researchers entering a new sub-field, such a tool can substantially reduce the time required to identify key contributions and understand methodological choices. The system also demonstrates a replicable architectural pattern for building section-aware RAG applications over long  structured documents.

---

## 🏗️ Architecture

- Presentation: React frontend (Vite)
- API: FastAPI backend serving read bundles and orchestration endpoints
- Extraction: modular pipelines (`IngestPipeline`, `MetadataExtractionPipeline`, `SectionHierarchyPipeline`)
- Retrieval: hybrid stack using BM25 + embeddings (Qdrant optional) and reranking
- Orchestration: LangGraph-based workflow graph (`backend/rag/graph.py`)

See module-level docs in `backend/` and `docs/` for detailed descriptions.

---

## 📁 Project Structure (high level)

```
backend/    # extraction, persistence, retrieval, LangGraph, API
frontend/   # React/Vite SPA
docs/       # design notes, evaluation reports
input/      # uploaded PDFs and extraction artifacts
output/     # evaluation and retrieval artifacts
```

Key entry points:
- Backend API: `backend/api/app.py` (`app = FastAPI(...)`)
- Workflow CLI: `backend/run.py` (`PaperAnalysisPipeline`)
- Extraction: `backend/extraction/extraction.py` (`PDFExtractor.extract`)
- Frontend bootstrap: `frontend/src/main.tsx`

---

## ⚙️ Setup & Quickstart

Prerequisites: Python 3.10+, Node.js (for frontend). Optional: PostgreSQL, Qdrant.

1. Create a virtual environment and install Python deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

2. Example environment variables (create `.env`):

```
GROQ_API_KEY=your_groq_key
POSTGRES_DSN=postgresql://user:password@localhost:5432/research_agent
VITE_API_BASE_URL=http://localhost:8000
QDRANT_URL=http://localhost:6333
```

3. Start the backend API:

```bash
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --reload
```

4. Start the frontend (separate terminal):

```bash
cd frontend
npm install
npm run dev
```

5. Run an extraction example:

```bash
python backend/run.py input/example.pdf --store-in-db
```

---

## ▶️ Usage

Typical flow:
1. Ingest a PDF (CLI or API)
2. Run extraction pipeline to produce structured artifacts
3. Persist artifacts to Postgres (optional)
4. Use frontend to browse papers and run QA
5. Run evaluation scripts in `backend/rag/retrieval/evaluation/` for metrics

API highlights:
- `GET /health` — service health
- `GET /api/papers` — list papers
- `GET /api/papers/{paper_id}/bundle` — get paper bundle for frontend

---

## 🧰 Technology Stack

- Backend: FastAPI, Uvicorn, Pydantic, SQLAlchemy
- Retrieval & LLMs: Groq, LangChain/LangGraph, HuggingFace embeddings, Qdrant (optional)
- Extraction: docling / docling-core, PyMuPDF
- Frontend: React, Vite, TanStack Query

See `requirements.txt` and `backend/requirements.txt` for concrete versions.

---

## 🛠️ Developer Notes

- Important modules: `backend/extraction/*`, `backend/rag/*`, `backend/api/*`, `backend/database/*`.
- Environment variables control DB, model keys, and retrieval behavior (`POSTGRES_DSN`, `GROQ_API_KEY`, `QDRANT_URL`, etc.).
- For retrieval evaluation, place datasets under `input/eval/` and run the evaluation script.

If you want numeric evaluation outputs added to this README, point me to the run results under `output/evaluation/` or `docs/` and I will insert them.

---

## ✅ Testing

Run unit tests with `pytest`:

```bash
pytest
pytest tests/test_validation.py -v
pytest --cov=backend --cov-report=term-missing
```

---

## 🤝 Contributing & License

Contributions welcome — see `docs/REORGANIZATION_SUMMARY.md` and `docs/IMPLEMENTATION_SUMMARY.md` for roadmap items. The project is MIT-licensed (see LICENSE file if present).

---

If you'd like, I can also:
- Add a concise `docker-compose` for Postgres + Qdrant + API + frontend
- Insert the latest evaluation numbers from a specified run file

9. `PaperViewer` renders section content and tracks visible section via `IntersectionObserver`
10. `InsightExtractor` renders tables/images from API bundle

---

## 5. Module and Component Breakdown

### Backend major modules

#### `backend/run.py`

- Purpose:
  - End-to-end orchestration for extraction + categorization + QA/summary
- Key symbols:
  - `PaperAnalysisPipeline.__init__`
  - `PaperAnalysisPipeline.run`
  - `_build_arg_parser`, `main`
- Depends on:
  - `get_agent` from `rag.graph`
  - optional `DBIngestionPipeline`
- Used by:
  - CLI invocation
  - scripts/examples importing pipeline

#### `backend/rag/graph.py`

- Purpose:
  - Defines LangGraph workflow and node logic
- Key symbols:
  - `extraction_node`, `categorizer_node`, `retrieve_and_qa_node`, `summarizer_node`
  - `applied_guide_node`, `theoretical_guide_node`, `survey_guide_node`
  - `route_after_categorizer`, `build_graph`, `get_agent`
- Depends on:
  - Groq (`ChatGroq`), retrieval pipeline, extraction orchestrator, prompts/models
- Used by:
  - `PaperAnalysisPipeline`

#### `backend/extraction/extraction.py`

- Purpose:
  - Extraction orchestrator that chains ingestion, metadata extraction, hierarchy extraction, and optional persistence
- Key symbols:
  - `PDFExtractor.extract`
  - `extract_pdf`
  - `_resolve_postgres_dsn`
- Depends on:
  - `IngestPipeline`, `MetadataExtractionPipeline`, `SectionHierarchyPipeline`, `PostgresPaperStore`
- Used by:
  - `extraction_node` in LangGraph
  - direct script execution

#### `backend/extraction/pipelines/ingest_pipeline.py`

- Purpose:
  - Validation + extraction + OCR + `ValidatedDocument` creation
- Key symbols:
  - `IngestPipeline.process`
  - `ValidationError`, `ExtractionError`
- Depends on:
  - `PDFValidator`, `PDFLoader`, `OCRHandler`
- Used by:
  - `PDFExtractor`

#### `backend/extraction/pipelines/metadata_pipeline.py`

- Purpose:
  - LLM-assisted metadata extraction from validated document
- Key symbols:
  - `MetadataExtractionPipeline.process`
- Depends on:
  - `MetadataExtractor`
- Used by:
  - `PDFExtractor`

#### `backend/extraction/pipelines/db_ingestion_pipeline.py`

- Purpose:
  - Persist docling-rich extraction into SQLAlchemy schema
- Key symbols:
  - `DBIngestionPipeline.ingest`
  - record builder helpers (`_build_section_record`, etc.)
- Depends on:
  - `DatabaseConnection`, `DocumentRepository`, rich extractor dataclasses
- Used by:
  - optional path in `PaperAnalysisPipeline.run`

#### `backend/api/app.py`

- Purpose:
  - FastAPI app that serves frontend-oriented read bundles
- Key symbols:
  - `_resolve_postgres_dsn`, `_make_store`
  - `health`, `list_papers`, `get_paper_bundle`
- Depends on:
  - `PostgresPaperStore`
- Used by:
  - frontend data client

#### `backend/database/*`

- Purpose:
  - SQLAlchemy schema and repository operations for document model persistence
- Key symbols:
  - `DatabaseConnection`
  - `DocumentRepository` methods (`upsert_document`, `get_sections_for_document`, etc.)
  - ORM models (`DocumentRecord`, `SectionRecord`, `TextBlockRecord`, ...)

### Frontend major components

#### `frontend/src/pages/Index.tsx`

- Purpose:
  - Main page container and data orchestration
- Key behaviors:
  - Fetches papers via `useQuery` and `getPapers`
  - Fetches bundle via `useQuery` and `getPaperBundle`
  - Wires section selection and viewport focus states

#### `frontend/src/components/PaperNavigation.tsx`

- Purpose:
  - Paper selector and section index
- Depends on:
  - `PaperSummary` types and callbacks from `Index`

#### `frontend/src/components/PaperViewer.tsx`

- Purpose:
  - Displays paper title/meta and section content
- Key symbols:
  - `PaperViewerHandle.scrollToSection`
  - `IntersectionObserver` section visibility tracking

#### `frontend/src/components/AIToolsPanel.tsx`

- Purpose:
  - Wraps insights and chat UI
- Depends on:
  - `InsightExtractor`, `ChatAssistant`

#### `frontend/src/lib/api.ts`

- Purpose:
  - API abstraction
- Key symbols:
  - `fetchJson<T>`, `getPapers`, `getPaperBundle`

---

## 6. API and Interfaces

### Exposed HTTP API endpoints

Base URL: `http://localhost:8000`

#### `GET /health`

- Handler: `health()` in `backend/api/app.py`
- Purpose: service and DB health
- Request:
  - no body
- Response shape:

```json
{
  "status": "ok",
  "db": "connected",
  "sample_count": 1
}
```

Failure mode may return:

```json
{
  "status": "degraded",
  "db": "error",
  "error": "..."
}
```

#### `GET /api/papers`

- Handler: `list_papers(limit: int = 100)`
- Purpose: list available papers
- Query params:
  - `limit` (optional int, default 100)
- Response shape:

```json
{
  "papers": [
    {
      "id": 1,
      "paper_name": "...",
      "title": "...",
      "abstract": "...",
      "source_pdf_path": "...",
      "created_at": "..."
    }
  ]
}
```

#### `GET /api/papers/{paper_id}/bundle`

- Handler: `get_paper_bundle(paper_id: int)`
- Purpose: return full frontend bundle
- Response shape:

```json
{
  "paper": {
    "id": 1,
    "paper_name": "...",
    "title": "...",
    "abstract": "..."
  },
  "sections": [
    {
      "id": "12",
      "title": "Introduction",
      "level": 1,
      "page_start": 1,
      "content": "...",
      "stats": {}
    }
  ],
  "tables": [],
  "images": [],
  "text_blocks": []
}
```

404 behavior:

```json
{
  "detail": "Paper not found"
}
```

### Internal interfaces between modules

- Pipeline state contract:
  - `AgentState` in `backend/rag/states.py`
  - Node functions in `backend/rag/graph.py` read/write this state dictionary
- Extraction contract:
  - `IngestPipeline.process` returns `ValidatedDocument`
  - `MetadataExtractionPipeline.process` returns `ProcessedDocument`
- Retrieval contract:
  - `RetrievalPipeline.query(...) -> list[RetrievalResult-like]`
- Frontend API contract:
  - TypeScript interfaces in `frontend/src/types/api.ts` (`PaperSummary`, `PaperSection`, `PaperBundle`)

---

## 7. Database and State Management

### Database schema(s)

Two persistence schemas coexist.

1. Legacy/API-facing schema (SQLAlchemy ORM path in `PostgresPaperStore.ensure_schema`):

- `papers`
- `sections`
- `text_blocks`
- `tables_data`
- `images`
- Link tables:
  - `section_text_blocks`
  - `section_tables`
  - `section_images`

Dedup constraints:

- Unique lower-cased `paper_name`
- Unique `pdf_hash` (when present)

2. SQLAlchemy schema (in `backend/database/models.py`):

- `documents`
- `sections`
- `text_blocks`
- `document_tables`
- `document_figures`
- `document_formulas`

### State management

- Backend workflow state:
  - `AgentState` carries query, extracted data, category, retrieval hits, answers, guide output, errors
- Frontend UI state:
  - local component state (`activeSection`, `focusedSection`, `selectedPaperId`) in `Index.tsx`
- Frontend remote state/cache:
  - TanStack Query cache via `QueryClient` and `useQuery`

### Caching layers and queues

- In-memory caches:
  - `_bm25_cache` in `RetrievalPipeline`
  - `_section_lookup_cache` in `rag/graph.py`
- On-disk retrieval artifacts:
  - BM25 encoder pickle per document in `output/{document_id}_bm25.pkl`
- Model cache:
  - `models/` via `MODEL_CACHE_DIR`
- Queue-like behavior:
  - Parallel question processing in `retrieve_and_qa_node` using `ThreadPoolExecutor`
- No message broker queue (Kafka/RabbitMQ/etc.) is currently implemented

---

## 8. Configuration and Environment

### Config files

- `config.py`: core runtime settings (API, upload, retrieval, Qdrant, LangSmith, feature flags)
- `backend/rag/retrieval/config.py`: retrieval-specific config resolution
- `frontend/vite.config.ts`: frontend dev server and alias config
- `pytest.ini`: test discovery, markers, coverage settings

### Environment variables used in code

API/app and general:

- `API_HOST`, `API_PORT`, `API_RELOAD`
- `UPLOAD_DIR`, `MAX_FILE_SIZE_MB`, `EXTRACTION_TIMEOUT`
- `CORS_ORIGINS`, `CORS_ALLOW_CREDENTIALS`
- `LOG_LEVEL`, `LOG_DIR`

LLM and observability:

- `GROQ_API_KEY`
- `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `LANGCHAIN_ENDPOINT`

Qdrant and retrieval:

- `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION_NAME`
- `DENSE_MODEL`, `DENSE_VECTOR_SIZE`
- `FINE_CHUNK_SIZE`, `FINE_CHUNK_OVERLAP`
- `COARSE_CHUNK_SIZE`, `COARSE_CHUNK_OVERLAP`
- `CHUNK_SIZE`, `CHUNK_OVERLAP`, `CHUNK_MIN_CHARS`
- `RETRIEVER_TOP_K`, `SCOPED_TOP_K`, `FALLBACK_TOP_K`, `RERANKER_TOP_N`, `QA_TOP_K`
- `MAX_GUIDE_QUESTIONS`, `MAX_REWRITE_QUERIES`, `MAX_PARALLEL_QUESTIONS`
- `RERANKER_MODEL`, `ENABLE_QUERY_REWRITE`, `REWRITE_MODEL`
- `MODEL_CACHE_DIR`, `OUTPUT_DIR`, `BM25_ENCODER_DIR`

Database connection options (both naming conventions appear in code):

- Direct DSN:
  - `POSTGRES_DSN`
  - `DATABASE_URL`
- Component vars in API path:
  - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
  - fallback aliases: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`
- Component vars in SQLAlchemy path:
  - `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, `PG_PASSWORD`

Frontend:

- `VITE_API_BASE_URL` (used in `frontend/src/lib/api.ts`)

### Local setup and run

1. Python environment and dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Frontend dependencies

```bash
cd frontend
npm install
cd ..
```

3. Configure environment (example)

```env
GROQ_API_KEY=your_key
POSTGRES_DSN=postgresql://user:password@localhost:5432/research_agent
VITE_API_BASE_URL=http://localhost:8000
```

4. Start backend API

```bash
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --reload
```

5. Start frontend

```bash
cd frontend
npm run dev
```

6. Run extraction/analysis workflow (example)

```bash
python backend/run.py input/paper.pdf --query "What is the main contribution?" --store-in-db
```

7. Optional: pre-download retrieval models for offline use

```bash
python download_models.py
```

---

## 9. Dependencies and Third-Party Integrations

### External services/APIs called

- Groq API:
  - Used for categorization, summarization, guide generation, and QA
  - Models referenced in code include `llama-3.1-8b-instant` and `llama-3.3-70b-versatile`
- Qdrant:
  - Used for hybrid retrieval indexing/search (dense + sparse vectors)
- LangSmith (optional):
  - Trace/observability for LangGraph runs when enabled

### Key third-party libraries and why

- `docling` / `docling-core`: rich PDF structure extraction
- `pymupdf`: low-level PDF validation and handling
- `langgraph`: explicit stateful orchestration of analysis flow
- `langchain-groq`: chat model integrations for prompts and structured outputs
- `sqlalchemy`: relational modeling and repository-backed persistence
- `psycopg`: PostgreSQL driver for SQLAlchemy persistence
- `qdrant-client`: vector index operations
- `rank-bm25`: sparse lexical retrieval
- `flashrank`: reranking of retrieval candidates
- `@tanstack/react-query`: frontend data fetching and cache lifecycle

---

## 10. Known Patterns and Conventions

### Naming and coding conventions observed

- Python:
  - `snake_case` for functions/variables
  - `PascalCase` for classes (`PaperAnalysisPipeline`, `DatabaseConnection`)
  - Type hints used broadly (`Optional`, `dict[str, Any]`, etc.)
- TypeScript/React:
  - `PascalCase` component names
  - `camelCase` hooks, handlers, and props
  - typed interfaces centralized in `frontend/src/types/api.ts`
- Data model naming:
  - Pydantic models for in-memory pipeline semantics
  - SQLAlchemy `*Record` classes for relational persistence entities

### Error handling strategy

- Explicit custom exceptions in ingestion layer:
  - `IngestionError`, `ValidationError`, `ExtractionError`
- Node-level try/except in LangGraph nodes populates `errors` array in state
- API uses `HTTPException(404, "Paper not found")` for missing paper bundles
- Fallback behavior:
  - Retrieval can degrade to dense-only if BM25 encoder absent (`_DenseFallbackSparseEncoder`)
  - Route fallback to `summarizer` for unknown category

### Logging and monitoring approach

- Python logging is used throughout (`logging.getLogger(__name__)`)
- `run.py` sets consistent log format and level from `LOG_LEVEL`
- `config.py` ensures log directory exists (`LOG_DIR.mkdir(exist_ok=True)`)
- Optional LangSmith tracing in `get_agent()` when `LANGCHAIN_TRACING_V2=true`

---

## Additional Notes

- Some markdown/docs files in the repo are historical and may describe older paths (for example, upload endpoints or removed files). The runtime truth for this README was derived from current executable modules.
- Frontend `ChatAssistant` currently uses mock response data (`mockResponses`) and is not wired to a backend Q&A endpoint.

## Testing

Main test suite lives in `tests/` and is configured via `pytest.ini`.

Typical commands:

```bash
pytest
pytest tests/test_validation.py -v
pytest --cov=backend --cov-report=term-missing
```

The repository includes historical testing summaries in `tests/TESTING_SUMMARY.md`.

pg_isready -h localhost -p 5432

./.venv/bin/python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8001 --reload

python3 - << 'PY'
import urllib.request, urllib.error
for url in ['http://127.0.0.1:8001/health','http://localhost:8080']:
try:
with urllib.request.urlopen(url, timeout=6) as r:
print(url, r.status, r.headers.get('content-type'))
except Exception as e:
print(url, 'ERR', e)
