# Research Paper Assistant — Complete Technical Audit

Generated: 2026-05-08

This document is a code-grounded, exhaustive technical audit of the Research Paper Assistant repository. It is intended to give an AI architect all the implementation- and system-level detail required to redesign this project into an advanced research-paper tutor.

Contents (sections)
1. SYSTEM OVERVIEW
2. FULL PROJECT STRUCTURE
3. ENTRY POINTS
4. DOCUMENT INGESTION PIPELINE
5. RETRIEVAL SYSTEM
6. PROMPT SYSTEM
7. LLM ORCHESTRATION
8. CURRENT RESEARCH PAPER ANALYSIS CAPABILITIES
9. KNOWLEDGE REPRESENTATION
10. FRONTEND ANALYSIS
11. CONFIGURATION + ENVIRONMENT
12. PERFORMANCE + SCALABILITY
13. ARCHITECTURAL WEAKNESSES
14. TRANSFORMATION READINESS
15. RECOMMENDED NEXT ARCHITECTURE
16. FINAL EXECUTIVE SUMMARY


---

## 1. SYSTEM OVERVIEW

- What the system currently does
  - Ingests research paper PDFs, extracts structured artifacts (title, abstract, sections, text blocks, figures, tables), persists metadata and artifacts, indexes text into a hybrid retrieval stack (dense + sparse + reranker + Qdrant), and provides a FastAPI backend + React frontend for browsing, reading-guide generation (Three-Pass method), and retrieval-driven Q&A.
  - Core orchestrator for reading-guide generation and retrieve-and-qa flows is a LangGraph workflow. See `backend/extraction/extraction.py`, `backend/rag/graph.py` and `backend/rag/prompts.py`.

- Primary use cases
  - Upload PDF → extraction → reading-guide generation (deferred or immediate)
  - Ask paper-specific questions via chat → retrieval → LLM answer
  - Browse extracted sections, figures, and tables in the UI

- User flow (request lifecycle: user input → final output)
  1. Frontend uploads PDF to `/api/papers/upload` (`backend/api/app.py`).
  2. Upload handler saves PDF and triggers ingestion (`IngestPipeline.process`) via background tasks or direct call (`backend/extraction/pipelines/ingest_pipeline.py`).
  3. Extraction produces artifacts in `input/` (e.g., `<uuid>_complete.json`, `<uuid>_hierarchy.json`, `<uuid>_fulltext.txt`), persists to Postgres via `PostgresPaperStore` and may enqueue indexing. See `backend/extraction/persistence.py` and `backend/api/app.py` background handlers.
  4. If indexing is configured, `RetrievalPipeline.index()` tokenizes/sections→chunks→embeds→indexes into Qdrant (`backend/rag/retrieval/pipeline.py`, `backend/rag/retrieval/indexing/qdrant_store.py`).
  5. Guide generation uses LangGraph `generate_reading_guide_state` and Pydantic schemas in `backend/rag/guide_models.py`. The workflow may defer per-question answer generation.
  6. When user asks a question, API assembles a short retrieval context from top chunks (`_build_qa_context_from_chunks` in `backend/api/app.py`) and calls the LLM with `qa_prompt` from `backend/rag/prompts.py`.

- Main outputs
  - Extraction artifacts (JSON, text files) under `input/` and derived `output/` artifacts.
  - Qdrant collection of vector points (hybrid dense + sparse vectors).
  - Reading guide JSON persisted to DB and accessible at `/api/papers/{paper_id}/guide` (`backend/api/app.py`).
  - Per-question answers stored via APIs/endpoints used by frontend chat.

- Supported features (concrete)
  - Adaptive OCR (selective page OCR) via `backend/extraction/app/ocr.py`.
  - Section-aware chunking and hierarchical section metadata preservation using `SectionChunker` and `Chunk` contract (`backend/rag/retrieval/chunking/section_chunker.py` and `backend/rag/retrieval/chunking/models.py`).
  - Hybrid retrieval: dense encoder (`BAAI/bge-small-en-v1.5`) + BM25 sparse per-doc + Qdrant fusion + FlashRank reranker (`backend/rag/retrieval/search/hybrid_retriever.py` and `backend/rag/retrieval/search/reranker.py`).
  - TF-IDF paper categorizer for APPLIED/THEORETICAL/SURVEY via `backend/rag/tfidf_categorizer.py`.
  - Technical-term extraction subsystem in `backend/extraction/technical_terms/`.
  - LangGraph-based reading guide orchestration (`backend/rag/graph.py`) with planner → question generation → per-question retrieval → QA nodes.

- Current limitations (concrete)
  - No multimodal figure understanding pipeline (figures are stored as references but not semantically interpreted).
  - Single-process LangGraph + local model loading limits concurrency and scalability.
  - LLM outputs expected as free-form JSON are brittle and rely on retries; no enforced function-calling or strict JSON schema prompting in all places.
  - No explicit learner model or user-adaptive tutoring; guides are paper-centric static outputs.

- Primary system classification: HYBRID (RAG + pipeline orchestration + limited agent workflows). The system is primarily a RAG/retrieval system with pipeline orchestration and agentic workflows for guide generation.

Mermaid flow (high-level):

```mermaid
flowchart TD
  U[User/Frontend] -->|upload| API[/api/papers/upload]
  API --> Ingest[IngestPipeline.process()]
  Ingest --> Extract[PDFLoader / OCR / MetadataPipeline]
  Extract --> Persist[PostgresPaperStore.persist_extraction]
  Persist --> Index[Indexer.index() → Qdrant]
  Index --> Retrieval[RetrievalPipeline.query()]
  Retrieval --> Rerank[FlashRankReranker]
  Retrieval -->|context| LLM[LLM (Groq/ChatGroq)]
  LLM --> API
  API --> U
  subgraph GUIDE
    Extract --> LangGraph[generate_reading_guide_state()]
    LangGraph --> Persist
  end
```

---

## 2. FULL PROJECT STRUCTURE

Below is a near-complete tree and explanation of important files and folders. I list purpose, key dependencies, role in pipeline, and whether critical.

Top-level (selected):
- `config.py` — global configuration values (models, chunk sizes, Qdrant, feature flags). Critical. (See: `FINE_CHUNK_SIZE`, `DENSE_MODEL`, `QDRANT_URL`, etc.)
- `backend/` — all server-side Python code. Critical.
- `frontend/` — React app (Vite + TypeScript). Important.
- `input/`, `output/`, `pdfs/` — file artifacts and storage. Important.
- `models/` — model cache. Important.
- `docs/` — design docs (this file will be saved here).

Selected backend tree (summary):

- `backend/api/app.py` — FastAPI app with routes: health, auth, paper CRUD, upload, guide endpoints, chat/qa endpoints. Critical. Uses `PostgresPaperStore`, `IngestPipeline`, `generate_reading_guide_state`, and retrieval helpers. Key endpoints:
  - `/api/papers/upload` (upload + start ingestion) — [app.py:L1479]
  - `/api/papers/{paper_id}/guide` — retrieve guide — [app.py:L1453]
  - `/api/papers/{paper_id}/chat` — chat endpoint — [app.py:L1636]
  - Other management endpoints (list papers, CMS endpoints) — view file.

- `backend/extraction/` — ingestion and extraction subsystem. Critical.
  - `pipelines/ingest_pipeline.py` — orchestrates PDF validation → loading → OCR (adaptive) → deduplication → returns `ValidatedDocument`. Critical.
  - `app/pdf_loader.py` — loader wrapper (PyMuPDF/docling/unstructured). Critical.
  - `app/ocr.py` — adaptive OCR with confidence heuristics. Important.
  - `persistence.py` — `PostgresPaperStore` persistence helpers and DB upserts. Critical.
  - `technical_terms/` — technical-term detection and definition lookup. Optional/valuable.

- `backend/rag/` — reading-guide workflows and retrieval stack. Critical for RAG.
  - `graph.py` — LangGraph workflow nodes and orchestration for categorization, guide generation, retrieve-and-qa flows. Critical.
  - `prompts.py` — central prompt templates for retrieval, QA, summarization, reading guide (applied/theoretical/survey). Critical.
  - `guide_models.py` — Pydantic models (schemas) for reading guides and planner steps. Important.
  - `tfidf_categorizer.py` — TF-IDF + logreg classifier artifacts loader for paper categorization. Useful.

- `backend/rag/retrieval/` — retrieval implementation. Critical.
  - `pipeline.py` — `RetrievalPipeline` orchestrates chunking → encoding → indexing → retrieval → reranking.
  - `chunking/` — chunk model, token-aware splitter, section-aware chunker. (See `models.py`, `section_chunker.py`, `text_splitter.py`.)
  - `embeddings/` — `dense_encoder.py` (BGE wrapper) and `sparse_encoder.py` (BM25 per-document). Critical.
  - `indexing/qdrant_store.py` — Qdrant collection manager & payload index creation. Critical.
  - `search/` — hybrid retriever logic and cross-encoder reranker (`hybrid_retriever.py`, `reranker.py`). Important.

- `backend/database/` — DB helpers and test scripts (connection helper, setup). Important.

- `backend/evaluation/` — evaluation scripts for retrieval and answers. Optional but useful for tuning.

Frontend selected files:
- `frontend/src/App.tsx` — root React component, routing via react-router and TanStack Query. Entry point.
- `frontend/src/pages/Index.tsx` — main page with upload, paper list, viewer, chat, AI tools panel.
- `frontend/src/components/` — `PaperViewer.tsx`, `ChatAssistant.tsx`, `PaperNavigation.tsx`, `AIToolsPanel.tsx`, `MarkdownMessage.tsx` — UI components. Important.

Docs and miscellaneous: plenty of docs in `docs/` explaining design decisions, quickstarts, and extraction notes.

---

## 3. ENTRY POINTS

- Backend entrypoint for server: `backend/api/app.py` defines `app = FastAPI(...)` and routes; run via Uvicorn:

```bash
uvicorn backend.api.app:app --reload --host 127.0.0.1 --port 8001
```

- CLI entry: `backend/run.py` — orchestrates full pipeline runs and uses `rag.graph.get_agent` for graph-run orchestration. Useful for offline runs and debugging.

- Ingestion triggers and async jobs:
  - `POST /api/papers/upload` triggers ingestion; handler may run long tasks in FastAPI `BackgroundTasks` or thread pool. See `_extract_and_update_paper` in `backend/api/app.py`.
  - `_generate_and_store_reading_guide` runs as a background task to call `generate_reading_guide_state` and persist guide results; failures saved in DB. See `backend/api/app.py`.

- Worker-style jobs (current state): there is no external queue system (e.g., Celery) by default — background work runs within the API process via FastAPI BackgroundTasks or ThreadPoolExecutor in `rag.graph.py` (some functions use thread pools). For production at scale, move these to a real worker queue.

- Frontend entry: `frontend/src/main.tsx` and `frontend/src/App.tsx` are the app entrypoints; run using `npm run dev` (Vite) in `frontend/`.

---

## 4. DOCUMENT INGESTION PIPELINE (EXACT DETAILS)

Flow and code locations:
- Orchestrator: `IngestPipeline.process(...)` in `backend/extraction/pipelines/ingest_pipeline.py`.
  - Steps: validation (`PDFValidator`), loading (`PDFLoader.load()`), selective OCR via `OCRHandler.process_if_needed()`, document model construction (`ValidatedDocument`), deduplication checks (optional), and return.

- PDF parsing libraries and OCR usage:
  - The loader wrapper abstracts several backends (PyMuPDF, docling, unstructured API). The actual loader implementation sits at `backend/extraction/app/pdf_loader.py` (inspect loader config flags `do_ocr`, `extract_images`, `extract_tables`).
  - OCR: `backend/extraction/app/ocr.py` supports `easyocr` or `tesseract` (default `easyocr`), with heuristics for page selection (`min_text_density`) and confidence scoring.

- Chunking strategy (exact):
  - Dual-level chunking: `FINE_CHUNK_SIZE = 150`, `FINE_CHUNK_OVERLAP = 30`, `COARSE_CHUNK_SIZE = 400`, `COARSE_CHUNK_OVERLAP = 60` (see `config.py`). The chunk creation uses a token-aware sliding window implemented in `backend/rag/retrieval/chunking/text_splitter.py` and `section_chunker.py`.
  - Section-aware: `section_chunker.py` assigns text to its section context and applies sliding windows inside section boundaries. Each chunk carries `section_path`, `section_path_ids` (canonical ID ancestry), `section_title`, `section_level`, and `element_ids` referencing figures/tables. The `Chunk` model is in `backend/rag/retrieval/chunking/models.py`.

- Metadata extraction and hierarchy detection:
  - `MetadataExtractionPipeline` and `SectionHierarchyPipeline` in `backend/extraction/pipelines/` produce section trees with `page_start`, `stats_json`, `content_snippet` fields; these are assembled for guides in `_build_sections_for_guide` in `backend/api/app.py`.

- Figures/Tables/Formulas:
  - Extracted as `extracted_elements` in the complete JSON artifacts. The ingestion persists counts and element IDs. Chunks for figure/table content use `content_type` and include `image_path` where applicable. No deep V-L reasoning is implemented (no figure captioning or diagram parsing service integrated).

- Citation extraction:
  - Reference section headings are recognized and excluded from retrieval using `_REFERENCE_SECTION_HEADING_RE` heuristics in `backend/rag/retrieval/search/hybrid_retriever.py`.

- Where chunking happens & indexing:
  - `RetrievalPipeline.index(...)` orchestrates chunking (via `section_chunker`), embedding (dense encoder + optional BM25 build), and writing to Qdrant via `Indexing.Indexer` and `QdrantStoreManager` (see `backend/rag/retrieval/pipeline.py` and `backend/rag/retrieval/indexing/qdrant_store.py`).

- Token and overlap specifics
  - Overlap and sizes are defined in `config.py`. Chunks below `CHUNK_MIN_CHARS` may be dropped. Token-count estimation stored as `token_count` in `Chunk` payload.


---

## 5. RETRIEVAL SYSTEM (DETAILED)

- Dense embedding model
  - `DenseEncoder` wraps `sentence_transformers.SentenceTransformer` using model `BAAI/bge-small-en-v1.5` by default (config `DENSE_MODEL`). Query-time uses a BGE query prefix internally. See `backend/rag/retrieval/embeddings/dense_encoder.py`.

- Sparse encoder
  - `BM25SparseEncoder` implemented under `backend/rag/retrieval/embeddings/sparse_encoder.py`. Encoders are persisted per-document as `*_bm25.pkl` and loaded by `RetrievalPipeline._get_sparse_encoder(document_id)`.

- Vector DB: Qdrant
  - `QdrantStoreManager` (`backend/rag/retrieval/indexing/qdrant_store.py`) creates a hybrid collection with two vector spaces and ensures payload indexes for fields: `document_id`, `section_title` (text index), `section_path`, `chunk_level`, `content_type`, `section_id`, `parent_section_id`, `section_path_ids`.
  - If `QDRANT_URL`/`QDRANT_API_KEY` not provided, manager can fall back to in-memory Qdrant client (development only).

- Hybrid retrieval flow
  - Implemented in `backend/rag/retrieval/search/hybrid_retriever.py`. The pipeline:
    1. Encode query dense + sparse.
    2. Issue hybrid search to Qdrant (RRF merging); apply payload filters (document_id, section_path_ids, content_type, exclude references).
    3. Merge, deduplicate candidates.
    4. Optional rerank with cross-encoder (FlashRank), call `rerank_results(...)` in `backend/rag/retrieval/pipeline.py`.

- Reranking
  - FlashRank local cross-encoder using `ms-marco-MiniLM-L-12-v2` controlled by `RERANKER_MODEL`. Implemented at `backend/rag/retrieval/search/reranker.py`. If `flashrank` not installed, reranking is disabled and the pipeline falls back to top-K.

- Query rewriting & orchestration
  - Optional LLM-based query expansion (`retriever_prompt`) controlled by `ENABLE_QUERY_REWRITE` and `REWRITE_MODEL` in `config.py`. Prompts live in `backend/rag/prompts.py`.

- Selection of chunks for QA
  - API builds a short context from a small number of chunks: `_build_qa_context_from_chunks(chunks, max_chunks=2)` found in `backend/api/app.py` (calls often use `QA_TOP_K` to retrieve a small number of supporting chunks). The final prompt uses `qa_prompt` wrapping context and metadata.

- Token budgeting
  - Token budgeting is coarse: the system limits chunk counts and rerank budgets (e.g., `RETRIEVER_TOP_K`, `RERANKER_TOP_N`), rather than fine-grained token-based truncation inside final prompts. Chunk sizes are configured to produce manageable prompt lengths, but explicit token-counting before final LLM call is not consistently enforced.


---

## 6. PROMPT SYSTEM (COMPLETE)

All prompts are centralized in `backend/rag/prompts.py`. Additional prompts exist in extraction fallback (`backend/extraction/app/groq_fallback.py`) and evaluation code (`backend/evaluation/*`). Below are the key prompts and analysis.

### `retriever_prompt(query, category, sections_to_read)` — `backend/rag/prompts.py`
- Purpose: LLM-driven query expansion to improve retrieval recall.
- Inputs: user query, paper category, optional list of priority sections.
- Output expected: a 1–3 sentence optimized query.
- Weakness: extra LLM call per query (latency + cost); output is raw text used downstream with no enforced structure.

### `qa_prompt(query, context, metadata)` — `backend/rag/prompts.py`
- Purpose: Answer user questions given retrieved context.
- Inputs: `query` (user), `context` (assembled top chunks), `metadata` (title, category).
- Outputs: free-text concise answer (format requested: direct answer then "Answer:").
- Weaknesses: no required machine-readable citations (IDs) in the prompt; hallucination risk where answer is not fully supported by context.

### `summarizer_prompt` and reading-guide prompts (`reading_guide_prompt`, `applied_guide_prompt`, `theoretical_guide_prompt`, `survey_guide_prompt`) — `backend/rag/prompts.py`
- Purpose: Create structured summaries and three-pass reading guides. `applied_guide_prompt` is explicit about referencing figures/tables and producing JSON.
- Inputs: title, abstract, flattened sections (snippets), sometimes introduction/conclusion.
- Outputs: JSON-shaped guide expected to match Pydantic schemas in `backend/rag/guide_models.py`.
- Weaknesses: LLM must return valid JSON conforming to Pydantic models; code implements validation and retry attempts but this pattern is fragile without function-calling or schema-enforced generation.

### Prompt chaining and planner
- The guide workflow chains: planner (skeleton pass) → guide generator (full pass) → per-step question generator (`guide_step_question_prompt`) → per-question retrieve-and-qa. Orchestration in `backend/rag/graph.py` ensures step extraction and section scoping via `_extract_guide_retrieval_info`.

### Hidden/system prompts
- Groq wrappers (`langchain_groq.ChatGroq`) are used across modules; the ChatGroq layer may add system-level instructions not visible in `prompts.py`.

### Evaluation prompts
- `backend/evaluation/evaluate_context_precision.py` and `backend/evaluation/evaluate_answers.py` contain judge prompts for offline evaluation of retrieved context and LLM answers.

Summary of prompt weaknesses
- Free-text outputs for JSON are fragile. Use of function-calling or JSON schema enforcement would increase reliability.
- No enforced citation format in QA outputs.
- Query rewrite can multiply LLM calls.


---

## 7. LLM ORCHESTRATION

- LLM frameworks in codebase
  - `langchain_groq.ChatGroq` used as the main LLM client in many places (e.g., `backend/api/app.py`, `backend/rag/graph.py`). Groq API keys are configured via `GROQ_API_KEY` in `config.py`.
  - LangGraph (`langgraph.graph`) used for orchestration of multi-node workflows in `backend/rag/graph.py`.
  - LangSmith tracing optionally integrated via `langsmith.run_helpers.traceable` when available.

- Models and roles (concrete mapping)
  - Groq (ChatGroq) — guide generation, extraction fallback prompts, query expansion when enabled.
  - Dense encoder: `BAAI/bge-small-en-v1.5` via sentence-transformers for document/query embeddings (`backend/rag/retrieval/embeddings/dense_encoder.py`).
  - Reranker: local FlashRank `ms-marco-MiniLM-L-12-v2` for cross-encoder reranking (`backend/rag/retrieval/search/reranker.py`).
  - Sparse BM25 encoder — local per-document encoder for sparse retrieval.
  - Optional rewrite model configured as `REWRITE_MODEL` (default `llama-3.1-8b-instant` in `config.py`) used when `ENABLE_QUERY_REWRITE` is true.

- Model routing logic
  - Categorizer uses TF-IDF model (fast artifact) to decide paper type and route to category-specific guide nodes.
  - Retrieval nodes use `RetrievalPipeline` which internalizes dense + sparse + rerank steps. Hybrid retriever falls back to dense-only on errors.
  - Reranker is lazy-loaded; if unavailable, pipeline returns top-K retrieval results.

- Fallback logic and robustness
  - Hybrid retriever catches exceptions and falls back to dense-only; reranker toggled off if `flashrank` missing.
  - Guide generation attempts validation and retry for ill-formed JSON. See `_GUIDE_VALIDATION_ATTEMPTS` logic in `backend/rag/graph.py`.

- Streaming and structured outputs
  - Frontend is prepared for streaming UX but backend LLM calls appear synchronous and return final answers. True chunked streaming endpoints are not obvious in `backend/api/app.py`.
  - Structured outputs: guides are intended to conform to `backend/rag/guide_models.py`. QA responses are free-text, not structured.

- Agent/Workflow framework
  - LangGraph is used for modular node orchestration (`backend/rag/graph.py`). The graph defines typed state and nodes for planner, retriever, summarizer, and QA.


---

## 8. CURRENT RESEARCH PAPER ANALYSIS CAPABILITIES

- How papers are analyzed
  - Structural extraction of title, abstract, sections with page numbers and text snippets. The pipeline constructs a section hierarchy and derives section content snippets, element counts, and text blocks.
  - Section-aware chunking ensures chunks carry breadcrumb context for retrieval.

- Summaries
  - `summarizer_prompt` generates category-aware structured summaries (applied/theoretical/survey). Called from `backend/rag/graph.py` when no query is supplied.

- Guides
  - Three-Pass reading guides implemented with planner + full guide templates and question generation. Schema enforced by `backend/rag/guide_models.py`.

- Section-aware parsing and retrieval
  - Yes: `section_path` and `section_path_ids` preserved and used for scoping retrieval.

- Figure understanding
  - Figures are extracted and stored as image paths and `content_type='figure'` chunks, but there is no V-L pipeline for figure interpretation.

- Citation understanding
  - Reference sections excluded from retrieval via heuristics; no citation graph or reference-resolved crosslinking is implemented.

- Pedagogical reasoning
  - Limited: the reading-guide encodes pedagogical structure but lacks personalization and iterative adaptation based on student answers.

- Paper classification
  - Implemented using TF-IDF artifacts (`backend/rag/tfidf_categorizer.py`).

Why outputs can be shallow
- Short retrieval context (few chunks) and single-shot LLM answers can produce surface-level responses; deeper critical reasoning requires multi-pass retrieval, internal verification, and richer assembled contexts (concept graphs), which the current pipeline does not implement fully.


---

## 9. KNOWLEDGE REPRESENTATION

- Current representation
  - Primary: Flat chunks stored as vector points in Qdrant, each carrying rich payload metadata (`section_path`, `section_id`, `element_ids`, `content_type`). See `backend/rag/retrieval/chunking/models.py`.

- Missing representations
  - No semantic concept graph, no citation graph, no persistent concept dependency maps. The orchestration graph (LangGraph) is a control-flow graph, not a knowledge graph.

- Conclusion: storage is chunk-centric with hierarchical section metadata; advanced graph structures must be added to enable concept-mapping or dependency tracking.


---

## 10. FRONTEND ANALYSIS

- UI architecture
  - React + Vite app in `frontend/`. Top-level `App.tsx` uses TanStack Query for server state and `react-router` for routes. Components render paper lists, viewer, navigation, and the chat/AI tools panel.

- State management
  - Local component state for UI interactions; TanStack Query handles fetching/caching for server APIs (`getPapers`, `getPaperBundle`, `getMe`, `uploadPaper` in `frontend/src/lib/api`).

- Rendering outputs and streaming
  - Chat messages rendered with markdown via `MarkdownMessage.tsx`. UI is prepared for streaming, but backend endpoints supply final results synchronously.

- File upload flow
  - Upload component posts to `/api/papers/upload` and shows progress; background extraction runs on the server and the frontend polls for progress or uses API endpoints to watch progress (`/api/papers/{paper_id}/progress`). See `frontend/src/pages/Index.tsx` and `frontend/src/components/EmptyStateUpload.tsx`.

- Multi-step workflow visualization
  - Reading guide displayed as a list of passes/steps with per-step questions; `PaperNavigation` and `PaperViewer` show sections and allow focus. UX is ready to support stepwise reading.


---

## 11. CONFIGURATION + ENVIRONMENT

- Key env vars in `config.py` (examples):
  - `GROQ_API_KEY` — Groq LLM key
  - `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION_NAME` — Qdrant config
  - `DENSE_MODEL`, `DENSE_VECTOR_SIZE` — dense encoder config
  - `RETRIEVER_TOP_K`, `RERANKER_TOP_N`, `QA_TOP_K` — retrieval tuning knobs
  - `ENABLE_QUERY_REWRITE`, `REWRITE_MODEL` — query rewrite control
  - `POSTGRES_DSN` or `POSTGRES_HOST/PORT/...` — Postgres connection

- Model cache
  - `MODEL_CACHE_DIR` used to store sentence-transformers and FlashRank artifacts; recommended for offline workloads.

- External services
  - Groq API (LLM), Qdrant Cloud (vector DB), Postgres for persistent storage. Unstructured API or Docling are optional dependencies for extraction.

- Docker / deployment
  - No single Dockerfile present in the repo snapshot. Deployment is via process managers: Uvicorn for FastAPI and `npm run dev`/`npm build` for frontend. A `setup_db.sh` exists for DB initialization.

- Local vs production differences
  - If Qdrant/Groq keys missing, the code warns and may fall back to in-memory Qdrant or disable features. Flags in `config.py` toggle tracing and features for dev vs prod.


---

## 12. PERFORMANCE + SCALABILITY

- Bottlenecks
  - Dense encoder (SentenceTransformers) heavy memory and first-load time. Lazy-loading reduces repeated startup cost but per-process memory remains large.
  - FlashRank reranker CPU usage if many reranking calls occur.
  - LangGraph runs performed in-process can block execution; background tasks are thread-based, not worker-queue based.

- Synchronous operations
  - Indexing and guide generation are expensive and not distributed. BackgroundTasks create concurrency limits tied to the API process.

- Redundant retrieval
  - Query rewriting increases LLM calls per query. Multi-question guide generation may run similar queries multiple times unless cached.

- Memory-heavy operations
  - Loading dense encoder + reranker into each API worker process will multiply memory usage. No centralized model-serving layer present.

- What will break at scale
  - High concurrency of uploads and guide generation will saturate CPU/memory. Without a worker queue, tasks will compete with API I/O. Qdrant scale depends on chosen cloud plan.

- Well-designed parts
  - Section-aware chunking and Qdrant payload schema are solid design choices for precise section-scoped retrieval.


---

## 13. ARCHITECTURAL WEAKNESSES (BRUTAL)

- Summarizer vs tutor behavior
  - The system is document-first: it generates guides/summaries based solely on paper structure and static LLM outputs, with no learner model or feedback-driven adaptation. That makes outputs more like static summarizations/guides than interactive pedagogical tutoring.

- Missing capabilities for advanced tutoring
  - No concept dependency mapping or persistent concept graph.
  - No figure-centric semantic analysis (figures remain image references, not parsed semantic content).
  - No student-adaptive sequencing (no user-model that tracks comprehension, misconceptions, or mastery).
  - LLM JSON outputs are brittle; current robustification is limited to retries. No function-calling or typed-response enforcement.

- Practical blockers to upgrade
  - In-process heavy model loading and lack of worker queue hinder scale-out.
  - Code expects local models and CPU inference (FlashRank), which is fine but requires orchestration changes to share models across workers.


---

## 14. TRANSFORMATION READINESS (KEEP / MODIFY / REMOVE / REBUILD)

- KEEP
  - Section-aware chunk model and Qdrant payload indexing (`backend/rag/retrieval/chunking/models.py`, `qdrant_store.py`).
  - FlashRank reranker as low-cost local cross-encoder option.
  - TF-IDF categorizer for quick paper-type routing.

- MODIFY
  - `RetrievalPipeline` to centralize token budgeting and expose model-server clients instead of local model loading.
  - `backend/rag/graph.py` to support multi-pass verification loops and schema-enforced LLM outputs.
  - `prompts.py` to shift to JSON-schema/function-calling patterns for reliability.

- REMOVE / REPLACE
  - Replace ad-hoc background threading for heavy tasks with a worker queue; remove reliance on in-process background tasks for heavy workloads.

- REBUILD
  - Model-serving layer (gRPC/HTTP) for dense encoder and reranker; a separate vision/figure understanding microservice; and a concept-graph builder service (Neo4j/RedisGraph).


---

## 15. RECOMMENDED NEXT ARCHITECTURE (ACTIONABLE)

Goal: evolve into an AI research-paper tutor with concept dependency mapping, figure-aware reasoning, and adaptive pedagogy.

Proposed architecture (component list)
1. Extraction Service (containerized worker)
   - Keep existing pipelines but run in dedicated worker pool (Celery/RQ/Prefect/Argo).
   - Output: enriched artifacts + concept candidates.

2. Model Serving Layer
   - Expose dense embedder, cross-encoder reranker, and (later) V-L figure models as networked services (BentoML/TorchServe/gRPC).
   - Advantages: shared memory, scaled replicas, easier GPU placement.

3. Vector DB + Concept Graph
   - Keep Qdrant for chunk storage. Add a graph DB (Neo4j or RedisGraph) for concepts; populate concept nodes and edges from extraction (use technical-term detection and relation extraction).

4. Workflow Orchestration
   - Move LangGraph nodes to a distributed orchestrator (Prefect or orchestrated LangGraph tasks). Use worker queues for heavy tasks.

5. Tutor Layer (new)
   - Student model store (Postgres/Redis) tracking mastery and prior answers.
   - Pedagogical planner agent that selects steps using concept graph and student model.
   - Assessment node: verifies user answers, updates student model.

6. UI Enhancements
   - Streaming endpoints for chat and guide generation.
   - Figure viewer with semantic overlays (captions, object highlights) powered by V-L service.

Migration strategy (phased)
1. Centralize models into a `model-server` process and change `RetrievalPipeline`/`FlashRank` to call it. (Small code changes). Improves memory usage immediately.
2. Implement worker queue for ingestion and guide generation — move heavy tasks out of API. Replace FastAPI BackgroundTasks with job enqueue. (Moderate).
3. Add concept extraction step and persist concepts to a graph DB. (Moderate).
4. Implement tutor-layer planner and student model; iterate UI for adaptive flows. (Major)

Tools & frameworks recommended
- Model serving: BentoML or custom gRPC microservices.
- Workflow: Prefect or Celery for durable queues.
- Concept graph: Neo4j or RedisGraph.
- Vector DB: Qdrant (keep).
- LLM: Groq or OpenAI with function-calling / schema enforcement, or a private LLM with structured outputs.


---

## 16. FINAL EXECUTIVE SUMMARY

- Current architecture summary
  - Monorepo: FastAPI backend for uploads and API, React frontend, extraction + RAG pipelines in `backend/`. Hybrid retrieval (dense BGE + BM25 sparse + Qdrant) and local FlashRank reranker. LangGraph orchestrates guide generation and retrieval flows.

- Biggest weaknesses
  - No figure understanding service, no concept graph, no student-modeling/adaptive tutoring, and brittle LLM JSON outputs. Heavy reliance on in-process model loads and thread-based background execution.

- Biggest opportunities
  - Reuse strong section-aware chunking and Qdrant schema; add concept extraction, model-serving, and a lightweight tutor layer to transform guides into interactive, adaptive learning sequences.

- Fast, high-impact upgrades
  1. Centralize model serving to reduce memory duplication.
  2. Replace in-process background tasks with a worker queue (Celery/Prefect).
  3. Enforce structured LLM outputs (function-calling / JSON schema) to reduce parsing errors.

- Technical debt
  - Fragile JSON parsing from LLMs; in-process heavy tasks; repeated model loads across processes.

- Estimated complexity to transform into a tutor
  - Moderate→High. Phased approach with model-server and worker queue first reduces risk.


---

### Key code references (selected)
- API & routes: `backend/api/app.py`
- Extraction orchestrator: `backend/extraction/pipelines/ingest_pipeline.py`
- OCR: `backend/extraction/app/ocr.py`
- LangGraph orchestration: `backend/rag/graph.py`
- Prompts: `backend/rag/prompts.py`
- Guide schemas: `backend/rag/guide_models.py`
- Retrieval pipeline: `backend/rag/retrieval/pipeline.py`
- Dense encoder: `backend/rag/retrieval/embeddings/dense_encoder.py`
- Qdrant manager: `backend/rag/retrieval/indexing/qdrant_store.py`
- Chunk models & chunker: `backend/rag/retrieval/chunking/models.py`, `backend/rag/retrieval/chunking/section_chunker.py`
- Reranker: `backend/rag/retrieval/search/reranker.py`
- TF-IDF categorizer: `backend/rag/tfidf_categorizer.py`
- Frontend entry: `frontend/src/App.tsx`, `frontend/src/pages/Index.tsx`


---

If you want, I can:
- (A) Commit this file and create a PR branch.
- (B) Generate an itemized migration backlog (PR-sized tasks) with estimates.
- (C) Implement one of the quick wins (model server client stub or worker queue transition).

Which step should I take next?
# Research Paper Assistant — Technical Audit

*Date: 2026-05-08*

This document is a code-grounded, exhaustive technical audit of the Research Paper Assistant repository. It is intended for an AI architect who will redesign the system into an advanced AI research-paper tutor. All claims reference concrete files and locations inside the repository.

---

## 1. SYSTEM OVERVIEW

### What the system currently does

- Ingests PDF research papers, extracts structured artifacts (title, abstract, sections, text blocks, figures, tables), persists extraction results and metadata, indexes chunked content into a hybrid vector store (Qdrant), and exposes an API + React frontend for browsing, Q&A, and Three-Pass reading guide generation. Key orchestrator and interfaces: [backend/extraction/extraction.py](backend/extraction/extraction.py), [backend/rag/graph.py](backend/rag/graph.py), [backend/api/app.py](backend/api/app.py).

### Primary use cases

- Upload a PDF, receive an extracted bundle and a Three-Pass reading guide.
- Ask questions about a paper (chat), receive retrieval-grounded answers.
- Browse paper sections and extracted artifacts in the React UI.

### User flow (end-to-end)

1. Frontend uploads PDF to `POST /api/papers/upload` ([backend/api/app.py#L1479]).
2. Backend triggers ingestion: `IngestPipeline.process()` ([backend/extraction/pipelines/ingest_pipeline.py]) which calls `PDFLoader` and `OCRHandler` when needed ([backend/extraction/app/pdf_loader.py], [backend/extraction/app/ocr.py]).
3. Extraction artifacts (e.g., `<uuid>_complete.json`, `<uuid>_hierarchy.json`, `<uuid>_fulltext.txt`) are written to `input/` and metadata persisted via `PostgresPaperStore` ([backend/extraction/persistence.py]).
4. Optional indexing: `RetrievalPipeline.index()` builds chunks (section-aware chunker) and writes points to Qdrant via `QdrantStoreManager` ([backend/rag/retrieval/pipeline.py], [backend/rag/retrieval/indexing/qdrant_store.py]).
5. Guide generation is a LangGraph workflow via `generate_reading_guide_state` ([backend/rag/graph.py]) and stored back to the DB; per-question retrieval + QA are executed as needed.
6. Chat endpoints assemble retrieval context and call LLM with `qa_prompt` to produce answers ([backend/api/app.py], [backend/rag/prompts.py]).

### Main outputs

- Extraction artifacts in `input/` (full text, hierarchy, complete JSON). See `extract_pdf` usage in [backend/extraction/extraction.py].
- Qdrant collection points with payload metadata (section ids, titles, chunk_level). See [backend/rag/retrieval/indexing/qdrant_store.py].
- Reading guides persisted in Postgres and returned by `/api/papers/{paper_id}/guide` ([backend/api/app.py#L1453]).
- Answers and per-question QA (persisted and retrievable) via API endpoints.

### Supported features

- Adaptive OCR; section-aware chunking; hybrid retrieval (dense + sparse BM25); local reranker (FlashRank); LangGraph workflows for guide generation.
- TF-IDF paper categorizer for APPLIED/THEORETICAL/SURVEY ([backend/rag/tfidf_categorizer.py]).
- Technical-term extraction subsystem ([backend/extraction/technical_terms/service.py]).

### Current limitations

- Figures/tables preserved as artifacts but not deeply interpreted (no integrated V-L figure understanding pipeline).
- No student/user model — guides are static per-paper and not personalized.
- In-process model loading and LangGraph runs create scaling bottlenecks.
- LLM JSON output is fragile; parsing retries exist but remain brittle.

### System classification

This repository implements a hybrid RAG + pipeline + agentic system: it is primarily a RAG/retrieval system with pipeline orchestration and agentic guide-generation workflows (LangGraph). Key retrieval pieces are in `backend/rag/retrieval` and orchestration is in `backend/rag/graph.py`.


```mermaid
flowchart TD
  U[User/Frontend] -->|upload| API[/api/papers/upload]
  API --> Ingest[IngestPipeline.process()]
  Ingest --> Extract[PDFLoader / OCR / MetadataPipeline]
  Extract --> Persist[PostgresPaperStore.persist_extraction]
  Persist --> Index[Indexer.index() → Qdrant]
  Index --> Retrieval[RetrievalPipeline.query()]
  Retrieval --> Rerank[FlashRankReranker]
  Retrieval -->|context| LLM[LLM (Groq/ChatGroq)]
  LLM --> API
  API --> U
  subgraph GUIDE
    Extract --> LangGraph[generate_reading_guide_state()]
    LangGraph --> Persist
  end
```

---

## 2. FULL PROJECT STRUCTURE

Below is a focused, complete tree of critical project folders and the role of each important file (omitting large node_modules and known static assets). Files are annotated with purpose, dependencies, pipeline role, and criticality.

Repository root highlights (critical files/folders):

- `config.py` — central configuration constants (chunk sizes, model names, Qdrant/Groq keys, feature flags). Critical. See: [config.py](config.py).
- `backend/` — Python backend (API, extraction, rag/retrieval, DB). Critical.
- `frontend/` — React + Vite UI. Important for UX.
- `input/`, `output/`, `pdfs/` — extraction inputs and artifacts. Important.
- `models/` — local model cache. Important for offline use.

Detailed backend breakdown (important files):

- `backend/api/app.py` — FastAPI app and endpoints (auth, paper listing, upload, guide endpoints, chat endpoints). Critical. Key routes: `/api/papers/upload`, `/api/papers/{paper_id}/chat`, `/api/papers/{paper_id}/guide`.

- `backend/extraction/` — ingestion and extraction pipelines
  - `pipelines/ingest_pipeline.py` — `IngestPipeline` orchestrator: validation, PDF loading, OCR, deduplication. Critical for ingestion.
  - `app/pdf_loader.py` — loader wrapper for PyMuPDF / docling / unstructured. Critical for extraction.
  - `app/ocr.py` — `OCRHandler` (adaptive page-level OCR). Important.
  - `persistence.py` — `PostgresPaperStore` persistence of paper metadata and artifacts. Critical.
  - `models/` — Pydantic models describing `ValidatedDocument`, pages, text blocks. Important.
  - `technical_terms/` — terminology detection and definition lookup (`service.py`, `detector.py`). Optional/valuable.

- `backend/rag/` — LangGraph + retrieval
  - `graph.py` — LangGraph workflow nodes that implement categorization, guide planning, per-question retrieval and QA orchestration. Critical for guide generation logic.
  - `prompts.py` — all central LLM prompts (retriever_prompt, qa_prompt, summarizer_prompt, reading_guide_prompt, applied/theoretical/survey prompts). Critical.
  - `states.py` — Pydantic state contracts used by LangGraph flows. Important.
  - `tfidf_categorizer.py` — offline TF-IDF categorizer (trained artifacts in `models/tfidf`). Important.
  - `retrieval/` — retrieval pipeline and submodules (critical)
    - `pipeline.py` — `RetrievalPipeline`: indexing, retrieve_with_section_scope, reranking orchestration. Critical.
    - `chunking/` — `section_chunker.py`, `text_splitter.py`, `models.py` define the chunk contract and section-aware chunking. Critical.
    - `embeddings/` — `dense_encoder.py` (BGE wrapper), `sparse_encoder.py` (BM25 wrapper). Critical.
    - `indexing/qdrant_store.py` — Qdrant collection manager and payload index definitions. Critical.
    - `search/hybrid_retriever.py` — hybrid dense+sparse retrieval logic. Critical.
    - `search/reranker.py` — FlashRank cross-encoder reranker. Important.

- `backend/database/` — DB connection helpers used by `PostgresPaperStore`. Important.

- `backend/run.py` — CLI for running analysis pipeline end-to-end (calls LangGraph). Useful for offline runs.

Frontend (high-level):

- `frontend/src/App.tsx` — React app root and routes. Entry point.
- `frontend/src/pages/Index.tsx` — main page wiring: upload, auth, viewer.
- `frontend/src/components/PaperViewer.tsx` — central UI for paper rendering.
- `frontend/src/components/ChatAssistant.tsx` — chat UI and API integration for `/api/papers/{id}/chat`.

Docs and tests:
- `docs/` — design notes, quickstarts, extraction guides (useful for system knowledge). Important.
- `tests/` — pytest suite for retrieval and pipeline tuning. Useful for validation.


---

## 3. ENTRY POINTS

### Backend entrypoints

- FastAPI app: `app = FastAPI(...)` defined in [backend/api/app.py#L932]. Launch via Uvicorn example in development: `uvicorn backend.api.app:app --reload --host 127.0.0.1 --port 8001`.

- CLI pipeline: `python backend/run.py` — runs LangGraph analysis pipeline for a single PDF (extraction → categorization → QA/summary) ([backend/run.py]).

- Worker/background actions: FastAPI `BackgroundTasks` is used for background work such as `_extract_and_update_paper` and `_generate_and_store_reading_guide` in [backend/api/app.py]. These are executed on the FastAPI worker thread pool.

### Frontend entrypoints

- Vite dev server: `npm run dev` from `frontend/` (entry `frontend/src/main.tsx` and `frontend/src/App.tsx`). `Index.tsx` is the main page.

### API routes (highlights)

- `GET /health` — health check ([backend/api/app.py#L943]).
- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` — auth endpoints.
- `GET /api/papers` — list papers ([backend/api/app.py#L1019]).
- `POST /api/papers/upload` — upload paper and start ingestion ([backend/api/app.py#L1479]).
- `GET /api/papers/{paper_id}/bundle` — retrieve persisted bundle of extraction data ([backend/api/app.py#L1159]).
- `GET /api/papers/{paper_id}/guide` — get generated reading guide ([backend/api/app.py#L1453]).
- `POST /api/papers/{paper_id}/chat` — chat endpoint performing retrieval + QA ([backend/api/app.py#L1636]).

### Workflow triggers

- Upload triggers `IngestPipeline.process()` and then background guide generation via `_generate_and_store_reading_guide()` in `backend/api/app.py`.
- Manual endpoints can trigger indexing and guide generation via dedicated admin routes (CMS endpoints exist under `/api/cms/*`). See [backend/api/app.py].


---

## 4. DOCUMENT INGESTION PIPELINE (EXACT)

This section describes the concrete extraction and indexing steps and where in the code each occurs.

### Orchestration
- Ingestion entry: `IngestPipeline.process()` in [backend/extraction/pipelines/ingest_pipeline.py]. The `IngestPipeline` composes `PDFValidator`, `PDFLoader`, and `OCRHandler`.

### PDF parsing libraries and OCR
- The loader (`PDFLoader`) abstracts between local PyMuPDF extraction and higher-level `docling` or `unstructured` pipelines (see implementation in [backend/extraction/app/pdf_loader.py]).
- OCR: `OCRHandler` (selective page-level OCR) uses `easyocr` or `tesseract` or docling's RapidOCR integration; logic in [backend/extraction/app/ocr.py]. It decides to OCR based on page-level text density heuristics (configurable `min_text_density`) and supports forced OCR via `force_ocr`.

### Chunking strategy
- Dual-level chunking (fine + coarse) implemented in [backend/rag/retrieval/chunking/text_splitter.py] and orchestrated by `section_chunker.py`.
  - Configured sizes in [config.py]:
    - `FINE_CHUNK_SIZE` = 150; `FINE_CHUNK_OVERLAP` = 30
    - `COARSE_CHUNK_SIZE` = 400; `COARSE_CHUNK_OVERLAP` = 60
  - The `section_chunker.py` assigns text to section nodes (from extracted hierarchy) and runs a token-aware sliding-window split inside each section so each chunk retains section context. See `Chunk` model in [backend/rag/retrieval/chunking/models.py].

### Metadata extraction
- Title, abstract, and sections are extracted by the metadata pipeline `MetadataExtractionPipeline` (under `backend/extraction/pipelines/`). Extraction fallback using Groq LLM to fill missing metadata lives in `backend/extraction/app/groq_fallback.py`.

### Figure / table handling
- Figures, tables, and formulas are detected during extraction and enumerated in `extracted_elements`. The chunk model supports `content_type` (`table`/`figure`) and `image_path` references. However, no deep visual reasoning pipeline is currently integrated; figure analysis beyond detection is not present.

### Citation & reference extraction
- Reference/Bibliography sections are recognized by heuristics (regex) and excluded from retrieval by default. See `_REFERENCE_SECTION_HEADING_RE` usages in retrieval modules.

### Indexing
- Indexer creates chunks, creates embeddings and BM25 sparse encoders (per-document `*_bm25.pkl`), and writes points to Qdrant via `QdrantStoreManager` in [backend/rag/retrieval/indexing/qdrant_store.py]. Indexer invoked by `RetrievalPipeline.index()`.


---

## 5. RETRIEVAL SYSTEM

### Embedding models used
- Dense encoder: `BAAI/bge-small-en-v1.5` default, via `sentence-transformers` wrapper `DenseEncoder` ([backend/rag/retrieval/embeddings/dense_encoder.py]). Query encoding applies a BGE-specific query prefix.
- Sparse encoder: BM25 implemented as `BM25SparseEncoder` (per-document encoder persisted as a pickle). See `backend/rag/retrieval/embeddings/sparse_encoder.py`.

### Vector DB
- Qdrant used for storage. Collection manager and payload schema handled in [backend/rag/retrieval/indexing/qdrant_store.py]. The collection defines a dense vector field and a sparse vector field and payload indexes for `document_id`, `section_title`, `section_path`, `chunk_level`, `content_type`, and `section_path_ids`.

### Retrieval pipeline
- `RetrievalPipeline` composes the components: dense encoder, sparse BM25 encoder, Qdrant store manager, and reranker ([backend/rag/retrieval/pipeline.py]).
- Hybrid retriever `HybridRetriever` performs a combined search (dense + sparse) and may fall back to dense-only if sparse fails ([backend/rag/retrieval/search/hybrid_retriever.py]).

### Reranking
- FlashRank local cross-encoder (`ms-marco-MiniLM-L-12-v2`) reranks candidates using `flashrank.Ranker` in [backend/rag/retrieval/search/reranker.py]. If unavailable, pipeline returns top-K retrieval hits.

### Filtering and section-scoped retrieval
- `retrieve_with_section_scope()` is implemented in `RetrievalPipeline` to filter by `section_path_ids` and include descendants (parent matches child sections). This enables per-step, section-aware retrieval used by the guide QA nodes ([backend/rag/graph.py] uses `_retrieve_with_section_id_scope`).

### Query rewriting and orchestration
- Optional LLM-based query expansion (`retriever_prompt`) in [backend/rag/prompts.py], controlled by `ENABLE_QUERY_REWRITE` in `config.py` and limited by `MAX_REWRITE_QUERIES`.

### Context assembly & token budgeting
- Context for QA is assembled by `_build_qa_context_from_chunks()` in [backend/api/app.py] and by per-question assembly in [backend/rag/graph.py]. The pipeline uses top-K chunk limits (`RETRIEVER_TOP_K`, `RERANKER_TOP_N`, `QA_TOP_K`) to bound tokens; however, final prompt token budgeting is coarse (by chunk count rather than strict token-trimming in the production prompt).


---

## 6. PROMPT SYSTEM (ALL PROMPTS)

All prompts are centralized under: [backend/rag/prompts.py](backend/rag/prompts.py). Additional prompts exist in extraction fallback utilities and evaluation. Below is an inventory with notes.

- `retriever_prompt(query, category, sections_to_read)` — builds a query-expansion prompt for LLM-based rewrite.
  - Purpose: improve retrieval by expanding query with section-focused terms.
  - Weakness: introduces an extra LLM call per query and relies on the LLM to return a short optimized query (no enforced schema).

- `qa_prompt(query, context, metadata)` — constructs a direct Q&A prompt.
  - Purpose: answer user questions using retrieved chunks.
  - Inputs: raw user query, concatenated context (one or more chunk texts), metadata (paper title, category).
  - Output format: free-text answer prefaced by short direct-answer instruction. Weakness: no explicit machine-readable citation requirement or JSON output enforcement.

- `summarizer_prompt(title, abstract, sections, category)` — structured summary prompt (300–500 words). Weakness: depth limited by input sections.

- `reading_guide_prompt(title, abstract, sections, category)` and specialized `applied_guide_prompt`, `theoretical_guide_prompt`, `survey_guide_prompt` — generate the Three-Pass guide.
  - Purpose: produce planner skeleton and detailed step lists with per-step questions.
  - Output expectation: JSON matching Pydantic schemas in [backend/rag/guide_models.py]. The system validates and retries if JSON malformed.
  - Weakness: reliance on perfect LLM JSON output; code includes validation attempts and fallback heuristics but still brittle.

- `applied_guide_planner_prompt`, `survey_guide_planner_prompt`, and `guide_step_question_prompt` — smaller prompts used in multi-node guide creation to generate planner skeletons and to refine per-step questions.

Other prompts:
- Extraction fallback prompts for metadata fill-in are in [backend/extraction/app/groq_fallback.py].
- Judgment/evaluation prompts are present in `backend/evaluation/` for evaluation tasks.

Prompt chaining and usage
- Top-level guide flow: planner prompt → guide generator → per-step question generator → per-question retrieval → `qa_prompt` for answers. This chain is implemented in [backend/rag/graph.py].


---

## 7. LLM ORCHESTRATION

### LLMs and where they are used
- Groq / `ChatGroq` used in many generator nodes and extraction fallback (see `langchain_groq.ChatGroq` usages in [backend/rag/graph.py] and [backend/api/app.py]).
- Dense embeddings: `BAAI/bge-small-en-v1.5` via `DenseEncoder` ([backend/rag/retrieval/embeddings/dense_encoder.py]).
- Reranker: FlashRank local cross-encoder `ms-marco-MiniLM-L-12-v2` ([backend/rag/retrieval/search/reranker.py]).
- Optional rewrite default `REWRITE_MODEL = llama-3.1-8b-instant` per `config.py`.

### Model routing and fallback
- `RetrievalPipeline` constructs `HybridRetriever` with dense + sparse encoders. If the hybrid call fails, it falls back to dense-only; if reranker unavailable, it returns top-K raw results (see `HybridRetriever` and `RetrievalPipeline.rerank_results`).
- TF-IDF is used for quick categorization before invoking heavier LLM-based guide templates; `_get_tfidf_categorizer()` returns a local `TfidfPaperCategorizer` ([backend/rag/graph.py]).

### Streaming & structured outputs
- The backend currently does synchronous LLM calls and returns the result to HTTP clients. The frontend displays outputs; explicit long-lived streaming (SSE / chunked HTTP) is not implemented in the main API endpoints. Client-side components are written to accept streaming-like updates but backend endpoints return completed responses.
- Structured outputs: guide generation expects JSON confirmed against Pydantic models in [backend/rag/guide_models.py]. This is an implicitly structured output, but enforcement is done via parsing and validation rather than via function-calling APIs.

### Orchestration frameworks
- LangGraph is the orchestration framework used for building and running graph nodes ([backend/rag/graph.py]). LangSmith traces are optionally supported if API key configured (see `config.py`).


---

## 8. CURRENT RESEARCH PAPER ANALYSIS CAPABILITIES

Concrete capabilities found in code:

- **Paper summaries**: `summarizer_prompt` used in `graph.py` to produce category-aware summaries ([backend/rag/prompts.py], [backend/rag/graph.py:call site]).
- **Three-Pass reading guide**: full implementation and schemas exist in [backend/rag/guide_models.py] and orchestration flows in [backend/rag/graph.py]. Guides include steps, objectives, questions, and expected outputs.
- **Section-aware parsing**: Hierarchy generation and section metadata available; chunking preserves section context and IDs ([backend/extraction/pipelines/section_hierarchy_pipeline.py], [backend/rag/retrieval/chunking/section_chunker.py]).
- **Figure detection**: Figures detected and persisted as element references (elements stored in extraction artifacts), but no deep figure reasoning pipeline.
- **Citation handling**: Reference sections recognized and excluded from retrieval via regex heuristics in retrieval modules.
- **Pedagogical reasoning**: The system encodes pedagogical structure (three-pass method) in prompts and schemas, but lacks adaptive pedagogy; no student model or multi-session personalization.
- **Paper classification**: TF-IDF + logistic regression artifact for classification into APPLIED/THEORETICAL/SURVEY exists ([backend/rag/tfidf_categorizer.py]).

Why outputs can be shallow
- Guided answers and summaries depend on retrieved chunks. If retrieval misses crucial chunks or the LLM is asked to extrapolate, the system may produce plausible but shallow outputs. Also, single-shot LLM generations for entire guide or summary may not explore multi-pass reasoning or cross-chunk synthesis.


---

## 9. KNOWLEDGE REPRESENTATION

- Primary representation: flattened indexed chunks with rich payload metadata (see `Chunk` model at [backend/rag/retrieval/chunking/models.py]).
- Section hierarchy: persisted as JSON/hierarchy sidecars and stored in DB ([backend/extraction/pipelines/section_hierarchy_pipeline.py]).
- No explicit semantic graph/knowledge graph: there is no persistent concept graph, citation graph, or concept-dependency map. Only chunk-level storage with payloads and auxiliary BM25 models are present.


---

## 10. FRONTEND ANALYSIS

- UI architecture: React + Vite, routed at `frontend/src/App.tsx`. State management uses TanStack Query for server state and local component state for UI. Key components: `PaperViewer.tsx`, `ChatAssistant.tsx`, `AIToolsPanel.tsx`.

- Rendering and streaming: Markdown messages rendered by `MarkdownMessage.tsx`. Chat UI expects synchronous responses. Frontend supports resizable guide and tools panels (see [frontend/src/pages/Index.tsx] resize handlers).

- File upload flow: `EmptyStateUpload.tsx` sends POST to `/api/papers/upload` and monitors progress; backend triggers background extraction.

- Multi-step visuals: The guide and per-step questions are rendered in side panels; component relationships are direct: Index → PaperViewer + PaperNavigation + ChatAssistant.


---

## 11. CONFIGURATION + ENVIRONMENT

Key environment variables and config entries (in `config.py`):

- `GROQ_API_KEY` — required for Groq API usage. See `config.py` warnings.
- `QDRANT_URL`, `QDRANT_API_KEY` — Qdrant Cloud endpoint and key.
- `DENSE_MODEL` (`BAAI/bge-small-en-v1.5` default), `RERANKER_MODEL` (`ms-marco-MiniLM-L-12-v2`).
- Chunking and retrieval knobs: `FINE_CHUNK_SIZE`, `COARSE_CHUNK_SIZE`, `RETRIEVER_TOP_K`, `RERANKER_TOP_N`, `QA_TOP_K`.
- DB connectivity: `POSTGRES_DSN` or `POSTGRES_HOST`/`POSTGRES_DB` etc. used by `PostgresPaperStore`.
- Feature flags: `ENABLE_QUERY_REWRITE`, `ENABLE_TECHNICAL_TERMS`, `LANGCHAIN_TRACING_V2`.

Deployment notes:
- No provided Dockerfile for full stack in repo snapshot — server launched via `uvicorn backend.api.app:app` and frontend via `npm run dev`/`npm run build`.


---

## 12. PERFORMANCE + SCALABILITY

Bottlenecks:
- Heavy model loads (dense encoder + FlashRank + LLM calls) performed inside the app process, which is memory-heavy and blocks scale.
- LangGraph workflows are executed in-process; large workloads or many concurrent uploads will fill available thread pools.
- Reranking and BM25 model loads are CPU/memory intensive on the host.

What will break at scale:
- Simultaneous ingestion + indexing + guide generation on a single machine will exhaust CPU/memory due to multiple models being loaded.

What is well designed:
- Hybrid retrieval (dense + sparse) + section-scoped retrieval and payload indexing are robust and enable precise scoping. Qdrant indexing schema is thoughtful.


---

## 13. ARCHITECTURAL WEAKNESSES (BRUTAL)

- Lack of student model / personalization — system is paper-centric, not learner-centric.
- No concept dependency modeling or semantic graphs; everything is chunk-based. This prevents building concept sequencing and curriculum generation.
- Figures are referenced but not interpreted — critical for many papers.
- Orchestration is in-process and monolithic; replace with distributed workers / model-serving layer for scale.
- Reliance on free-form LLM JSON output is fragile and causes retries / brittle parsing.


---

## 14. TRANSFORMATION READINESS (KEEP / MODIFY / REMOVE / REBUILD)

- KEEP:
  - Section-aware chunk formats and Qdrant payload schema (`backend/rag/retrieval/chunking/models.py`, `qdrant_store.py`).
  - TF-IDF categorizer artifact and logic for quick paper type classification.

- MODIFY:
  - `RetrievalPipeline` to add token-aware prompt builders and a centralized query-expansion cache.
  - LangGraph guide nodes to use structured-output function-calls or JSON-schema enforcement.

- REMOVE / REPLACE:
  - Replace ad-hoc background thread launches with a proper task queue for heavy jobs.

- REBUILD:
  - Build a model-serving layer to host dense embedder and reranker (gRPC/BentoML) so many processes can share models without duplication.
  - Add a concept-extraction pipeline and graph DB to represent concept dependencies.


---

## 15. RECOMMENDED NEXT ARCHITECTURE (ACTIONABLE PLAN)

Goal: Transform into an AI research-paper tutor with concept mapping, figure awareness, and pedagogical sequencing.

1. Operational improvements (low-medium effort):
   - Move heavy models (BGE embedder, FlashRank reranker) into a shared model-serving microservice. Update `RetrievalPipeline` to call the service. (Benefit: memory reuse).
   - Replace FastAPI background threads with a worker queue (e.g., Celery / RQ / Prefect / Ray Tasks) and enqueue ingestion/indexing/guide tasks.

2. Knowledge-layer improvements (medium effort):
   - Implement a Concept Extractor service: extract named concepts, definitions, and dependencies (use technical-term detector as starting point). Store concept nodes in a graph DB (Neo4j or RedisGraph).
   - Add a citation parsing / reference linking component to construct a citation graph.

3. Tutor-layer features (higher effort):
   - Build a student model store (per-user knowledge state). Update guide planner to produce adaptive steps based on assumed prior knowledge and observed answers.
   - Add figure-understanding pipeline: multimodal model to caption and extract relations from diagrams (Vision-Language model; use CLIP/BLIP + custom parsers).

4. LLM and prompt hardening
   - Migrate key prompt outputs to function-calling or JSON-schema enforced LLM calls (reduce parsing fragility).
   - Add verification nodes in LangGraph: generate → verify (retrieval-backed) → finalize.

Migration strategy (phased):
- Phase 1: Model server + task queue (2–4 weeks).
- Phase 2: Concept extractor + graph, plus student model (4–8 weeks).
- Phase 3: Figure reasoning and tutor adaptivity (4–12 weeks).

Recommended tooling: Qdrant (keep), Neo4j/RedisGraph (concept graph), BentoML/gRPC (model serving), Prefect/Ray (orchestration), LangGraph (keep for orchestration but make nodes call remote services).


---

## 16. FINAL EXECUTIVE SUMMARY

- **Current architecture:** Hybrid RAG + LangGraph orchestration + FastAPI + React. Core files: [backend/api/app.py](backend/api/app.py), [backend/extraction/pipelines/ingest_pipeline.py](backend/extraction/pipelines/ingest_pipeline.py), [backend/rag/graph.py](backend/rag/graph.py), [backend/rag/retrieval/pipeline.py](backend/rag/retrieval/pipeline.py).

- **Biggest weaknesses:** Monolithic in-process model usage, no student personalization, lack of figure and concept graph reasoning, and fragile LLM output parsing.

- **Biggest opportunities:** Reuse the section-aware chunking and Qdrant payload design, add a concept graph and figure-understanding service, centralize model serving and task queue.

- **Fast wins:** Move models to a shared server; convert background work to a queue; adopt JSON-schema/function-calls for LLM outputs.

- **Estimated complexity:** Moderate–High. A phased approach yields early wins (model server + worker queue) then enables larger capabilities (concept graph, tutor adaptivity).


---

### Key code references

- API & primary routes: [backend/api/app.py](backend/api/app.py)
- Ingest pipeline: [backend/extraction/pipelines/ingest_pipeline.py](backend/extraction/pipelines/ingest_pipeline.py)
- LangGraph orchestration: [backend/rag/graph.py](backend/rag/graph.py)
- Prompts: [backend/rag/prompts.py](backend/rag/prompts.py)
- Retrieval pipeline and indexer: [backend/rag/retrieval/pipeline.py](backend/rag/retrieval/pipeline.py)
- Chunk models & chunker: [backend/rag/retrieval/chunking/models.py](backend/rag/retrieval/chunking/models.py), [backend/rag/retrieval/chunking/section_chunker.py](backend/rag/retrieval/chunking/section_chunker.py)
- Qdrant store manager: [backend/rag/retrieval/indexing/qdrant_store.py](backend/rag/retrieval/indexing/qdrant_store.py)
- Guide schemas: [backend/rag/guide_models.py](backend/rag/guide_models.py)


---

If you want I can now:
- Create a prioritized implementation backlog (PR-sized tasks) to migrate the system toward the tutor architecture, or
- Implement one low-effort change now (e.g., enforce JSON-schema validation for the reading guide by wrapping current prompt calls and adding a robust parsing/repair loop), or
- Start building a model-serving shim for the dense encoder.

Tell me which next step you prefer and I'll proceed.
