# ResearchAgent

ResearchAgent is a full-stack system for ingesting research PDFs, extracting structured artifacts, storing them in PostgreSQL, and serving/visualizing them through a FastAPI + React application. The repository also includes a LangGraph-based analysis workflow (categorization, guide generation, retrieve-and-QA) and a separate technical-term detection subsystem.

This README is codebase-grounded and references concrete modules, classes, and functions currently in the repo.

---

## 1. Project Overview

### What this project does

Core outcomes from a PDF:

- Validates and loads PDFs (`PDFValidator`, `PDFLoader`, `IngestPipeline`)
- Extracts metadata and structure (`MetadataExtractionPipeline`, `SectionHierarchyPipeline`)
- Persists extracted content into PostgreSQL with deduplication (`PostgresPaperStore.persist_extraction`, `DocumentRepository.upsert_document`)
- Exposes read APIs for paper browsing (`/api/papers`, `/api/papers/{paper_id}/bundle`)
- Renders papers, sections, tables, and figures in the frontend (`Index`, `PaperViewer`, `InsightExtractor`)
- Runs analysis workflows with LangGraph (`get_agent`, `retrieve_and_qa_node`, category guide nodes)

Primary runtime pipelines:

1. Extraction pipeline via `backend/extraction/extraction.py` (`PDFExtractor.extract`)
2. Unified analysis pipeline via `backend/run.py` (`PaperAnalysisPipeline.run`) and `backend/rag/graph.py`
3. Read API pipeline via `backend/api/app.py`

### Tech stack and key dependencies

Backend (Python):

- FastAPI `>=0.104.0` and Uvicorn `>=0.24.0`
- Pydantic `>=2.0.0`
- Docling `>=2.0.0` + `docling-core>=2.0.0`
- Groq client `>=0.9.0`
- LangChain/LangGraph (`langchain-groq`, `langchain-core`, `langgraph`)
- SQLAlchemy `>=2.0.0`
- psycopg `>=3.1.x`
- Retrieval stack: `qdrant-client>=1.7.0`, `rank-bm25>=0.2.2`, `flashrank>=0.2.0`, `sentence-transformers>=2.2.0`, `transformers>=4.36/4.37`

Frontend (TypeScript/React):

- React `^18.3.1`
- Vite `^5.4.19`
- React Router `^6.30.1`
- TanStack Query `^5.83.0`
- Tailwind CSS `^3.4.17`
- Radix UI component primitives (`@radix-ui/*`)
- Zod `^3.25.76`, React Hook Form `^7.61.1`

Source of versions:

- `requirements.txt`
- `backend/requirements.txt`
- `frontend/package.json`

### High-level architecture summary

System shape: layered monorepo with backend service + frontend app + extraction/analysis workers.

- Ingestion/analysis layer (Python): parse PDF, derive metadata/hierarchy, classify paper, retrieve answers
- Persistence layer (PostgreSQL): two data-access styles coexist
  - Legacy persistence schema used by frontend APIs: `papers`, `sections`, `text_blocks`, `tables_data`, `images`, link tables
  - SQLAlchemy rich schema for document-oriented storage: `documents`, `sections`, `text_blocks`, `document_tables`, `document_figures`, `document_formulas`
- API layer (FastAPI): read-only endpoints consumed by frontend
- Presentation layer (React): list papers, navigate sections, render content and extracted artifacts

---

## 2. Project Structure

### Repository-level breakdown

```text
ResearchAgent/
├── backend/                        # Python backend (API + extraction + rag + db)
├── frontend/                       # React/Vite UI
├── tests/                          # Pytest suite for ingestion modules
├── docs/                           # Design notes, quickstarts, implementation summaries
├── input/                          # Extraction artifacts (*.json, *.txt) per document UUID
├── output/                         # Retrieval/output artifacts (guides, indexes, sections)
├── models/                         # Local model cache (embeddings/reranker)
├── logs/                           # Runtime logs
├── playground/                     # Experimental notebooks and exploratory scripts
├── Technical term detector/        # Separate NLP subsystem for term detection/definition lookup
├── config.py                       # Global config constants and env parsing
├── requirements.txt                # Root Python dependencies
├── full_requirement.txt            # Extended dependency listing
├── pytest.ini                      # Test and coverage config
├── download_models.py              # Pre-download retrieval models
├── query_intro.py                  # DB query utility script example
├── test_run.py                     # End-to-end pipeline smoke script
├── PDTR_v2.md                      # Technical report / architecture context
└── README.md                       # This document
```

### Backend breakdown

```text
backend/
├── run.py                          # Main Python/CLI pipeline entry (`PaperAnalysisPipeline`)
├── api/
│   └── app.py                      # FastAPI app + HTTP routes
├── extraction/
│   ├── extraction.py               # Orchestrator (`PDFExtractor`)
│   ├── app/                        # PDF/OCR/metadata extractors and fallbacks
│   │   ├── validation.py           # `PDFValidator`
│   │   ├── pdf_loader.py           # `PDFLoader`
│   │   ├── ocr.py                  # `OCRHandler`
│   │   ├── metadata_extractor.py   # metadata extraction core
│   │   ├── section_detector.py     # section detection helpers
│   │   ├── groq_fallback.py        # LLM fallback helpers
│   │   └── docling_rich_extractor.py # rich element extraction for DB ingestion
│   ├── pipelines/
│   │   ├── ingest_pipeline.py      # `IngestPipeline`
│   │   ├── metadata_pipeline.py    # `MetadataExtractionPipeline`
│   │   ├── section_hierarchy_pipeline.py # `SectionHierarchyPipeline`
│   │   └── db_ingestion_pipeline.py # `DBIngestionPipeline`
│   ├── models/
│   │   ├── document.py             # `ValidatedDocument`, `PageContent`
│   │   ├── metadata.py             # `ExtractedMetadata`, `ProcessedDocument`
│   │   └── section_hierarchy.py    # `SectionHierarchy`, `SectionNode`
│   └── persistence/
│       ├── postgres_store.py       # Legacy persistence and API-facing queries
│       └── query_paper.py          # Query helper script
├── rag/
│   ├── graph.py                    # LangGraph nodes and routing (`build_graph`, `get_agent`)
│   ├── states.py                   # `AgentState`, `RetrievalResult`
│   ├── prompts.py                  # Prompt templates
│   ├── guide_models.py             # Structured guide schemas
│   └── retrieval/
│       ├── pipeline.py             # `RetrievalPipeline`
│       ├── config.py               # Retrieval env config
│       ├── chunking/               # Chunk generation models/splitters
│       ├── embeddings/             # Dense and sparse encoders
│       ├── indexing/               # Qdrant indexing/store abstractions
│       ├── search/                 # Hybrid retriever + reranker
│       └── evaluation/             # Retrieval evaluation notes
├── database/
│   ├── models.py                   # SQLAlchemy schema
│   ├── connection.py               # `DatabaseConnection`
│   └── repository.py               # `DocumentRepository`
└── examples/
    └── simple_workflow.py          # Sample runs for extraction/QA/summary
```

### Frontend breakdown

```text
frontend/
├── src/
│   ├── main.tsx                    # React bootstrap
│   ├── App.tsx                     # Router + QueryClientProvider
│   ├── pages/
│   │   ├── Index.tsx               # 3-panel app composition + data fetching
│   │   └── NotFound.tsx            # Fallback route
│   ├── components/
│   │   ├── PaperNavigation.tsx     # left panel (paper select + section nav)
│   │   ├── PaperViewer.tsx         # center panel (paper/section rendering)
│   │   ├── AIToolsPanel.tsx        # right panel container
│   │   ├── InsightExtractor.tsx    # figure/table/formula cards
│   │   └── ChatAssistant.tsx       # UI-only mock assistant
│   ├── lib/api.ts                  # fetch wrappers (`getPapers`, `getPaperBundle`)
│   └── types/api.ts                # API contracts
├── package.json                    # scripts + deps
└── vite.config.ts                  # dev server, aliases, plugin config
```

### Entry points

- Backend API server: `backend/api/app.py` (`app = FastAPI(...)`)
- Backend workflow CLI: `backend/run.py` (`main()`, `PaperAnalysisPipeline`)
- Extraction-only script: `backend/extraction/extraction.py` (`extract_pdf`, `PDFExtractor.extract`)
- Frontend SPA bootstrap: `frontend/src/main.tsx`
- Utility entry scripts: `download_models.py`, `test_run.py`, `query_intro.py`

---

## 3. Architecture and Design Patterns

### Architectural pattern

Primarily layered architecture with orchestrated pipelines:

- Presentation layer: React components and route composition
- API layer: FastAPI endpoints in `backend/api/app.py`
- Application orchestration layer:
  - `PaperAnalysisPipeline` (workflow orchestrator)
  - LangGraph node graph in `backend/rag/graph.py`
  - Extraction pipeline orchestration in `backend/extraction/extraction.py`
- Domain/data layer:
  - Pydantic domain models in `backend/extraction/models/*`, `backend/rag/states.py`
  - SQLAlchemy ORM models in `backend/database/models.py`
- Infrastructure layer:
  - PostgreSQL via SQLAlchemy ORM (psycopg driver)
  - Qdrant retrieval index
  - Groq API integration

### Key design patterns identified

- Pipeline pattern:
  - `IngestPipeline.process` -> `MetadataExtractionPipeline.process` -> `SectionHierarchyPipeline.process_from_processed_document`
- Orchestrator pattern:
  - `PDFExtractor.extract` and `PaperAnalysisPipeline.run` compose subsystems and control branching
- State machine/workflow graph:
  - LangGraph `StateGraph(dict)` in `build_graph()` with conditional route `route_after_categorizer`
- Repository pattern:
  - `DocumentRepository` encapsulates SQLAlchemy CRUD operations
- Singleton/lazy initialization:
  - `_agent` in `rag/graph.py`, `_retrieval_pipeline` in `rag/graph.py`, `_default_connection` in `database/connection.py`
- Adapter-like conversion builders:
  - `_build_section_record`, `_build_text_block_record`, etc. in `DBIngestionPipeline`

### Separation of concerns across modules

- `backend/api/*`: transport and response shaping only
- `backend/extraction/*`: ingest/extract/structure/persist document artifacts
- `backend/rag/*`: classification, guide generation, retrieval, QA, summarization
- `backend/database/*`: persistence contract and schema for SQLAlchemy path
- `frontend/src/lib/api.ts`: network boundary; UI components remain fetch-agnostic

---

## 4. Data Flow

### Data ingress

- PDF input from filesystem path:
  - CLI arg `pdf_path` in `backend/run.py`
  - Function arg in `PDFExtractor.extract(pdf_path, ...)`
- API query parameters and path params:
  - `GET /api/papers?limit=...`
  - `GET /api/papers/{paper_id}/bundle`
- Environment config via `os.getenv` in:
  - `config.py`
  - `backend/api/app.py` (`_resolve_postgres_dsn`)
  - `backend/database/connection.py` (`_build_database_url`)

### Internal data movement

Extraction path:

1. `IngestPipeline.process` validates, loads, optionally OCRs PDF -> `ValidatedDocument`
2. `MetadataExtractionPipeline.process` -> `ProcessedDocument`
3. `SectionHierarchyPipeline.process_from_processed_document` -> hierarchy model
4. `PDFExtractor.extract` writes artifact files and optionally persists through `PostgresPaperStore.persist_extraction`

LangGraph path:

1. `extraction_node` runs `PDFExtractor.extract` and maps result into workflow state
2. `categorizer_node` uses Groq model (`llama-3.1-8b-instant`) for category/confidence
3. Route decision in `route_after_categorizer`
4. Optional guide node (`applied_guide_node` | `theoretical_guide_node` | `survey_guide_node`)
5. `retrieve_and_qa_node`:
   - `RetrievalPipeline.index(...)` (if hierarchy file available)
   - scoped + fallback retrieval via `RetrievalPipeline.query(...)`
   - reranking via `rerank_results`
   - answer generation with Groq model (`llama-3.3-70b-versatile`)

API read path:

1. Frontend `getPapers()` -> `GET /api/papers`
2. Frontend `getPaperBundle(paperId)` -> `GET /api/papers/{id}/bundle`
3. `get_paper_bundle` queries store methods:
   - `get_paper_by_id`
   - `get_sections_for_paper_id`
   - `get_text_blocks_for_paper_id`
   - `get_tables_for_paper_id`
   - `get_images_for_paper_id`
   - `get_section_text_blocks_for_paper_id`
4. API composes normalized section content and returns bundle JSON

### Data egress

- Files written:
  - `input/{doc_id}_metadata.json`
  - `input/{doc_id}_hierarchy.json`
  - `input/{doc_id}_fulltext.txt`
  - `input/{doc_id}_complete.json`
  - `output/{document_id}_guide.json`
  - retrieval artifacts in `output/` (e.g., BM25 pickles, section lookup JSON)
- Database writes:
  - Legacy schema via `PostgresPaperStore.persist_extraction`
  - SQLAlchemy schema via `DBIngestionPipeline` + `DocumentRepository`
- HTTP responses:
  - FastAPI JSON payloads for health, list, bundle

### Step-by-step trace of the critical user flow

Flow: extract a paper, then view it in the UI.

1. User runs extraction (CLI):
   - `python backend/run.py input/paper.pdf --store-in-db`
2. `PaperAnalysisPipeline.run` invokes graph (`self._graph.invoke(initial_state)`)
3. `extraction_node` runs `PDFExtractor.extract` and writes artifacts
4. If DB configured, persistence stores paper and linked sections/text/tables/images
5. User starts API server (`uvicorn backend.api.app:app ...`)
6. Frontend loads (`frontend/src/pages/Index.tsx`)
7. `useQuery(['papers'])` calls `getPapers` and displays paper selector
8. Selecting a paper triggers `useQuery(['paper-bundle', paperId])`
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
