# Pipeline Diagnosis

## QUESTION 1: Why is Docling converting the PDF twice?

**ROOT CAUSE:** The ingest stage and metadata stage each run their own Docling conversion path. `extract_pdf()` first returns a `ValidatedDocument` from `IngestPipeline.process()`, then `MetadataExtractionPipeline.process()` hands `document.pdf_path` back into `MetadataExtractor`, which builds a fresh `DocumentConverter` and calls `convert()` again. There is no shared Docling object reused between the two stages.

**KEY LINES:**
- `backend/extraction/extraction.py` around the ingest and metadata steps.
- `backend/extraction/pipelines/ingest_pipeline.py` returns the `ValidatedDocument`.
- `backend/extraction/pipelines/metadata_pipeline.py` constructs `MetadataExtractor`.
- `backend/extraction/app/pdf_loader.py` initializes a `DocumentConverter` and converts the PDF.
- `backend/extraction/app/metadata_extractor.py` also initializes a `DocumentConverter` and converts the PDF.

**CONSEQUENCE:** The same PDF is converted once during ingestion and again during metadata extraction, duplicating Docling work for every upload.

## QUESTION 2: Why does chunking and indexing happen twice?

**ROOT CAUSE:** The graph path chunks once in `chunking_node`, but `indexing_node` ignores the in-memory chunks as the source of truth and creates a new `RetrievalPipeline`, which re-reads the hierarchy artifact and re-chunks through `Indexer.index_document()`. The graph is built on a plain `dict` state, not the `AgentState` model, so the intended typed contract is not what actually drives execution.

**KEY LINES:**
- `backend/extraction/extraction.py` invokes `agent.invoke(state)`.
- `backend/rag/graph.py` builds `StateGraph(dict)` and adds `chunking` and `indexing` nodes.
- `backend/rag/graph.py` chunking reads `state.get("metadata", {})` and `metadata.get("sections", [])`.
- `backend/rag/graph.py` indexing reads `state.get("chunks", [])`, then calls `pipeline.index(...)`.
- `backend/rag/graph.py` wires `retrieve_and_qa -> chunking -> indexing -> END`.
- `backend/rag/states.py` defines `AgentState`, but that model is not what `StateGraph` uses.

**CONSEQUENCE:** Chunking work is duplicated, and indexing is not driven by the chunks already produced in the graph.

## QUESTION 3: Why is DenseEncoder reloading on every request?

**ROOT CAUSE:** `DenseEncoder` itself is lazy, but not globally cached. It sets `self._model = None` and loads only inside `_load()`. `Indexer` does not create the encoder itself; it receives one via dependency injection. The cache lives only inside `RetrievalPipeline`, and graph-side indexing creates a fresh `RetrievalPipeline()` each time, which can recreate the encoder path. There is no module-level singleton or `lru_cache` in `dense_encoder.py`.

**KEY LINES:**
- `backend/rag/retrieval/embeddings/dense_encoder.py` sets `self._model = None` and loads in `_load()`.
- `backend/rag/retrieval/pipeline.py` lazily creates `DenseEncoder` in `_get_dense_encoder()`.
- `backend/rag/retrieval/pipeline.py` lazily creates `Indexer` in `_get_indexer()`.
- `backend/rag/graph.py` creates `RetrievalPipeline()` inside `indexing_node`.
- `backend/api/app.py` defers extraction to a background task.

**CONSEQUENCE:** The model stays warm only for the lifetime of one `DenseEncoder` instance. Any path that recreates the retrieval pipeline can cold-load the model again.

## QUESTION 4: Why does the UI receive the guide so late?

**ROOT CAUSE:** The upload endpoint intentionally returns before extraction finishes. It writes a pending paper row, schedules `_extract_and_update_paper()` using FastAPI `BackgroundTasks`, and immediately returns `guide_status = pending`. The bundle endpoint is a database read: it reports the current guide status and only returns a guide when the stored guide row is ready. There is no separate in-memory progress tracker.

**KEY LINES:**
- `backend/api/app.py` adds `_extract_and_update_paper` as a background task.
- `backend/api/app.py` returns `guide_status = {"status": "pending", ...}` immediately.
- `backend/api/app.py` `get_paper_bundle()` reads `guide_row = store.get_paper_guide_for_paper_id(paper_id)`.
- `backend/api/app.py` derives `guide_status` from stored DB fields.
- `backend/api/app.py` only substitutes `reading_guide` when the stored guide is ready.

**CONSEQUENCE:** The frontend sees the paper record quickly, but the guide appears later because it is generated after the response and surfaced only when the DB row changes.

## QUESTION 5: What is the overall pipeline entry point?

**ROOT CAUSE:** The HTTP upload handler is only the trigger. It schedules a background worker, and that worker runs the extraction path, the Qdrant indexing path, and then guide generation. The final `graph.invoke()` call happens inside `generate_reading_guide_state()` after `_generate_and_store_reading_guide()` calls it.

**KEY LINES:**
- `backend/api/app.py` defines `@app.post("/api/papers/upload")`.
- `backend/api/app.py` schedules `_extract_and_update_paper(...)` with `background_tasks.add_task(...)`.
- `backend/api/app.py` `_extract_and_update_paper()` calls `extract_pdf(...)`.
- `backend/api/app.py` `_extract_and_update_paper()` then calls `_index_paper_in_qdrant(...)` and `_generate_and_store_reading_guide(...)`.
- `backend/extraction/extraction.py` `extract_pdf()` constructs `PDFExtractor`.
- `backend/extraction/extraction.py` `PDFExtractor.extract()` runs ingest, metadata, hierarchy, and guide generation.
- `backend/extraction/extraction.py` `generate_reading_guide_state()` builds state and calls `agent.invoke(state)`.

**CONSEQUENCE:** The upload request itself is not synchronous end-to-end. Once the background task starts, the pipeline steps are sequential and blocking, but the request/response boundary is crossed before extraction, indexing, and guide generation complete.