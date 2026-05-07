# LangSmith Workflow Map — Research Paper Assistant

This document defines the end-to-end workflow for the Research Paper Assistant, mapping each processing node/stage with its inputs, outputs, and LangSmith trace emissions. Use this to monitor processing time, data transformations, and bottlenecks.

---

## Overview

The system follows this high-level flow:

```
PDF Input
   ↓
[1] Ingest Pipeline (validate, OCR, build ValidatedDocument)
   ↓
[2] Docling Rich Extractor (extract sections, text, tables, figures, formulas)
   ↓
[3] Metadata Pipeline (extract title, abstract, sections via Groq LLM)
   ↓
[4] Section Hierarchy Pipeline (build section tree from extracted metadata)
   ↓
[5] DB Ingestion Pipeline (persist rich extraction to PostgreSQL)
   ↓
[6] LangGraph Workflow Orchestration
   ├─→ [6a] Extraction Node (map extraction results to state)
   ├─→ [6b] Categorizer Node (classify: APPLIED/THEORETICAL/SURVEY)
   ├─→ [6c] Guide Node (generate 3-pass reading guide per category)
   ├─→ [6d] Retrieve & QA Node (retrieve chunks, answer questions in parallel)
   ├─→ [6e] Summarizer Node (generate paper summary)
   └─→ [7] Indexing & Chunking (section-aware chunking + dense/sparse embedding)
       └─→ [8] Qdrant Upsert (store vectors + metadata)

```

---

## Node-by-Node Breakdown

### **1. Ingest Pipeline** (`backend/extraction/pipelines/ingest_pipeline.py`)

**Purpose:** Validate PDF, detect/run OCR, extract basic page structure.

**Inputs (from state):**
- `pdf_path` (Path): file to ingest
- `force_ocr` (bool, optional): force OCR reprocessing

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `ingest_stage:start` | `{"pdf_path": "..."}` | Entry point; PDF file path logged |
| `ingest_stage:validated` | `{"pdf_hash": "abc123..."}` | PDF validated, hash computed |
| `ingest_stage:extracted` | `{"page_count": 42}` | Pages extracted via PyMuPDF or OCR |
| `ingest_stage:ocr_checked` | `{"was_reprocessed": true/false}` | OCR decision logged |
| `ingest_stage:document_built` | `{"document_id": "doc-uuid", "page_count": 42}` | ValidatedDocument created |

**Outputs (state mutations):**
- `document_id` (str): unique doc identifier
- `validated_document` (ValidatedDocument): PDF pages + text
- `extraction_metadata` (dict): page-level extraction stats

**⚠️ LangSmith Considerations:**
- Keep `pdf_path` as short filename only (not full path for security)
- Send counts only (page_count, hash length) — never send full page text
- If OCR reprocessing occurs, log flag but not OCR'd content

---

### **2. Docling Rich Extractor** (`backend/extraction/app/docling_rich_extractor.py`)

**Purpose:** Parse document structure; extract text blocks, formulas, tables, figures with rich metadata.

**Inputs:**
- `validated_document` (ValidatedDocument)
- `pdf_path` (Path)

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `docling_rich:start` | `{"pdf_path": "...", "pdf_hash": "abc..."}` | Begin extraction |
| `docling_rich:sections_extracted` | `{"num_sections": 15}` | Section tree parsed |
| `docling_rich:text_blocks_extracted` | `{"num_text_blocks": 345}` | Text blocks identified |
| `docling_rich:formulas_extracted` | `{"num_formulas": 28}` | Math formulas detected |
| `docling_rich:completed` | `{"document_id": "...", "total_elements": 500}` | Extraction finished |

**Outputs:**
- `RichSectionData[]`: sections with hierarchy
- `RichTextBlock[]`: text chunks with coordinates
- `RichTableData[]`: tables with structure
- `RichFigureData[]`: figures with captions
- `RichFormulaData[]`: formulas with LaTeX

**⚠️ LangSmith Considerations:**
- Send only **element counts** (num_sections, num_text_blocks, etc.)
- **Never** send full text content — send counts and IDs only
- Log section titles as short strings (first 50 chars) for debugging

---

### **3. Metadata Extraction Pipeline** (`backend/extraction/pipelines/metadata_pipeline.py`)

**Purpose:** Use Groq LLM + Docling output to extract structured metadata (title, abstract, keywords, sections).

**Inputs:**
- `validated_document` (ValidatedDocument)
- `docling_result` (DoclingRichResult)

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `metadata_stage:start` | `{"document_id": "doc-uuid"}` | Begin metadata extraction |
| `metadata_stage:extract_failure` | `{"error_type": "timeout", "attempt": 2}` | LLM call failed (caught & logged) |
| `metadata_stage:completed` | `{"document_id": "...", "processing_time_sec": 12.5, "fields_found": ["title", "abstract", "keywords"]}` | Metadata extracted successfully |

**Outputs:**
- `title` (str): paper title
- `abstract` (str): paper abstract
- `keywords` (list[str]): extracted keywords
- `sections` (list[dict]): section hierarchy from content

**⚠️ LangSmith Considerations:**
- Send `processing_time_sec` to track LLM latency
- Send list of **field names** found (not values) — title/abstract values are large
- If extraction fails, log error type but not full stack trace

---

### **4. Section Hierarchy Pipeline** (`backend/extraction/pipelines/section_hierarchy_pipeline.py`)

**Purpose:** Build hierarchical section tree (parent-child relationships, depth, numbering).

**Inputs:**
- `processed_doc` (ProcessedDocument) or `validated_doc` (ValidatedDocument)

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `section_stage:start` | `{"document_id": "...", "num_sections": 20}` | Begin hierarchy construction |
| `section_stage:completed` | `{"document_id": "...", "hierarchy_depth": 3, "root_sections": 5}` | Hierarchy complete |

**Outputs:**
- `SectionHierarchy`: nested tree with IDs, titles, levels, parent references

**⚠️ LangSmith Considerations:**
- Send structure stats (depth, root count) not full tree JSON
- Send unique section IDs (first 20 only) for validation

---

### **5. DB Ingestion Pipeline** (`backend/extraction/pipelines/db_ingestion_pipeline.py`)

**Purpose:** Convert extraction results to DB payloads; persist to PostgreSQL `papers` table.

**Inputs:**
- All extracted data (metadata, hierarchy, rich content)
- `document_id` (str)

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `db_stage:start` | `{"pdf_path": "...", "document_id": "doc-uuid"}` | Begin DB persistence |
| `db_stage:completed` | `{"document_id": "...", "stored": true, "paper_id": "paper-12345"}` | Record inserted/updated |

**Outputs:**
- `db_paper_id` (int): assigned database record ID
- `database` (dict): ingestion metadata (stored flag, timestamps)

**⚠️ LangSmith Considerations:**
- Send only `stored` flag (boolean) — not full row data
- Send assigned `paper_id` for downstream reference

---

### **6a. Extraction Node** (`backend/rag/graph.py` - LangGraph Workflow)

**Purpose:** Orchestration wrapper; calls PDFExtractor and maps results to workflow state.

**Inputs (from state):**
- `pdf_path` (str): input file

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `node:extraction_start` | `{"pdf_path": "paper.pdf"}` | Extraction node entered |
| `node:extraction_completed` | `{"document_id": "uuid", "title_present": true, "abstract_len": 320}` | Extraction node finished |

**State Mutations:**
- `document_id`, `full_text`, `title`, `abstract`, `sections`, `hierarchy`, `extraction_files`, `database`

**Output to Next Node:**
- Complete extraction metadata + hierarchy

**⚠️ LangSmith Considerations:**
- Send `abstract_len` (int) — not abstract content
- Send `title_present` (bool) for validation

---

### **6b. Categorizer Node** (`backend/rag/graph.py`)

**Purpose:** Classify paper into APPLIED / THEORETICAL / SURVEY using TF-IDF + logistic regression.

**Inputs (from state):**
- `title` (str), `abstract` (str)

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `node:categorizer_start` | `{"title_len": 45, "abstract_len": 250}` | Categorization started |
| `node:categorizer_completed` | `{"category": "APPLIED", "confidence": "HIGH"}` | Category assigned |

**State Mutations:**
- `category` (str): one of {APPLIED, THEORETICAL, SURVEY}
- `confidence` (str): one of {HIGH, MEDIUM, LOW}
- `category_reasoning` (str): brief explanation

**Output to Next Node:**
- Category determines which guide node runs next (routing decision)

**⚠️ LangSmith Considerations:**
- Send category name and confidence level only
- Omit reasoning text (can be verbose)

---

### **6c. Guide Generation Node** (`backend/rag/graph.py` - applied_guide_node, theoretical_guide_node, survey_guide_node)

**Purpose:** Generate a 3-pass structured reading guide (extraction questions, key concepts, synthesis questions) specific to paper category.

**Inputs (from state):**
- `title`, `abstract`, `sections`, `full_text`, `document_id`

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `node:guide_{LABEL}_start` | `{"document_id": "uuid", "title_len": 50, "abstract_len": 300}` | Guide generation started (LABEL = APPLIED/THEORETICAL/SURVEY) |
| `node:guide_{LABEL}_completed` | `{"document_id": "uuid", "num_questions": 12, "num_sections": 8, "valid": true}` | Guide finalized (passes validation) |

**State Mutations:**
- `reading_guide_plan` (dict): structured guide JSON
- `reading_guide` (dict): finalized guide after validation
- `question_section_pairs` (list[dict]): per-question section mappings
- `questions_to_answer` (list[str]): flat question list
- `sections_to_read` (list[str]): flat section list

**Output to Next Node:**
- Question-section pairs ready for retrieval

**⚠️ LangSmith Considerations:**
- Send `num_questions`, `num_sections`, `valid` (boolean) only
- **Never** send full guide content
- Send validation status to debug guide quality issues

---

### **6d. Retrieve & QA Node** (`backend/rag/graph.py`)

**Purpose:** For each guide question (or user query), retrieve top-K relevant chunks from Qdrant and generate answers using Groq LLM.

**Inputs (from state):**
- `question_section_pairs` (list[dict]) or `query` (str)
- `document_id` (str)

**Subprocess: Indexing** (if not already done)
- Chunks document sections → embeddings → Qdrant upsert

**Trace Events (Retrieval):**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `node:retrieve_and_qa_start` | `{"document_id": "uuid", "num_pairs": 10}` | QA loop started |
| `node:retrieve_and_qa_indexing_completed` | `{"document_id": "uuid", "total_questions": 10}` | Indexing finished, questions ready |
| `node:retrieve_and_qa_completed` | `{"document_id": "uuid", "answers_generated": 10}` | All answers generated (or deferred) |

**Trace Events (Per-Question Retrieval — from `_retrieve_for_question`):**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `retrieval_stage:query_expansion` | `{"question": "What is X?", "expanded_queries": ["What is X?", "Explain X"]}` | Query expanded |
| `retrieval_stage:section_scope_resolution` | `{"query_section": "3.2", "resolved_sections": ["3.2", "3.2.1"]}` | Section scope expanded (descendants included) |
| `retrieval_stage:scope_retrieval` | `{"section_id": "3.2", "hits": 8}` | Scoped retrieval returned results |
| `retrieval_stage:fallback_retrieval` | `{"reason": "low_recall", "fallback_hits": 5}` | Full-doc retrieval fallback triggered |
| `retrieval_stage:reranking` | `{"input_count": 13, "output_count": 5}` | Reranking applied |
| `chat_answer_input` | `{"question": "...", "final_input_count": 5, "chunks": [...previews...]}` | Ready for QA LLM |

**State Mutations:**
- `per_question_results` (list[dict]): per-question retrieval metadata
- `retrieval_results` (list[dict]): top chunks for display
- `qa_results` (list[dict]): answers with confidence scores

**Output to Next Node:**
- Answers ready for display or further processing

**⚠️ LangSmith Considerations:**
- Send `num_pairs`, `answers_generated` (counts only)
- Send expanded query list (first 3 only) + hit counts
- Send chunk previews (first 100 chars + ID, not full content)
- Never send full chunk content to LangSmith

---

### **6e. Summarizer Node** (`backend/rag/graph.py`)

**Purpose:** Generate an abstractive summary of the paper using Groq LLM.

**Inputs (from state):**
- `title`, `abstract`, `sections`, `category`

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `node:summarizer_start` | `{"title_len": 50, "abstract_len": 250, "category": "APPLIED"}` | Summarization started |
| `node:summarizer_completed` | `{"document_id": "uuid", "summary_len": 1200, "num_contributions": 4}` | Summary generated |

**State Mutations:**
- `summary` (str): abstractive summary
- `key_contributions` (list[str]): extracted key points

**Output to Display:**
- Summary text ready for user

**⚠️ LangSmith Considerations:**
- Send `summary_len` (int) not the full summary
- Send `num_contributions` (count) not the list

---

### **7. Chunking** (`backend/rag/retrieval/chunking/section_chunker.py`)

**Purpose:** Split section text into token-aware chunks with section context (parent, level, path).

**Inputs:**
- `sections` (list[dict]): section data with text
- `paper_id` (str): document identifier

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `chunk_stage:start` | `{"paper_id": "uuid", "num_sections": 20}` | Chunking started |
| `chunk_stage:completed` | `{"paper_id": "uuid", "num_chunks": 345}` | All chunks created |

**Outputs:**
- `Chunk[]`: list of Chunk objects with section metadata

**⚠️ LangSmith Considerations:**
- Send input section count and output chunk count only
- Log chunk statistics (min/max/average size in tokens)

---

### **8. Indexing** (`backend/rag/retrieval/indexing/indexer.py`)

**Purpose:** Embed chunks (dense + sparse vectors); persist to Qdrant with metadata.

**Inputs:**
- `Chunk[]`: chunks to index
- `document_id` (str)

**Trace Events:**
| Stage | Payload | Purpose |
|-------|---------|---------|
| `index_stage:chunked` | `{"document_id": "uuid", "num_chunks": 345}` | Chunks received |
| `index_stage:embedding_start` | `{"document_id": "uuid", "num_chunks": 345}` | Dense/sparse encoding started |
| `index_stage:embedding_completed` | `{"document_id": "uuid"}` | Encodings ready |
| `index_stage:upsert_completed` | `{"document_id": "uuid", "total_chunks": 345}` | All chunks persisted to Qdrant |

**Outputs:**
- Chunks indexed in Qdrant with dense & sparse vectors
- BM25 encodings saved to disk

**⚠️ LangSmith Considerations:**
- Send chunk counts at each stage
- Never send embedding vectors themselves
- Log Qdrant upsert batch counts (e.g., "batch 1 of 3: 115 chunks")

---

## Timing Expectations & Bottlenecks

### Typical Processing Time by Stage (for 30-page PDF)

| Stage | Typical Duration | Bottleneck |
|-------|------------------|-----------|
| Ingest (validate + OCR) | 5–15 sec | OCR (if needed) |
| Docling Extraction | 8–12 sec | Document parsing |
| Metadata Extraction (LLM) | 15–30 sec | Groq API latency |
| Section Hierarchy | 2–3 sec | In-memory tree building |
| DB Ingestion | 1–2 sec | PostgreSQL write |
| **Subtotal (Ingestion Phase)** | **31–62 sec** | Metadata LLM |
| Categorization (TF-IDF) | 0.5–1 sec | Model inference |
| Guide Generation (LLM) | 20–40 sec | Groq API + validation retries |
| Chunking | 3–5 sec | Tokenization |
| Indexing (embedding + Qdrant) | 10–20 sec | Dense embedding model |
| **Subtotal (QA Phase)** | **30–65 sec** | Guide LLM + Indexing |
| Retrieve & QA (per question) | 3–8 sec | LLM answer generation |
| **End-to-End (ingestion + QA with 5 questions)** | **~1–2 min** | Guide LLM + embedding |

---

## Monitoring & Debugging Guide

### Key Metrics to Track in LangSmith

1. **Ingest Phase Timing:**
   - `ingest_stage:start` → `document_built`: Total ingestion time
   - Watch for OCR delays (compare `ocr_checked` flag)

2. **Metadata Extraction Quality:**
   - `metadata_stage:start` → `completed`: LLM latency
   - Check `fields_found` to ensure all metadata extracted

3. **Guide Quality:**
   - `guide_*_start` → `guide_*_completed`: Guide generation time
   - Check `valid` flag — if false, validation retries occurred

4. **Retrieval Performance:**
   - `retrieve_and_qa_start` → `indexing_completed`: Document indexing time
   - `retrieval_stage:scope_retrieval` → `reranking`: Retrieval pipeline latency
   - Compare `scope_retrieval` hits vs `fallback_retrieval` hits to assess section scoping quality

5. **QA Latency:**
   - Time from `chat_answer_input` to `node:retrieve_and_qa_completed`
   - If > 10 sec per question, investigate LLM latency or chunk retrieval

### Common Issues & Diagnostics

| Issue | Trace to Check | Action |
|-------|----------------|--------|
| High OCR latency | `ingest_stage:ocr_checked` flag is true | Consider turning off OCR for non-scanned PDFs |
| Missing metadata | `metadata_stage:completed` `fields_found` is short list | Check Groq API quota / network |
| Invalid guide | `guide_*_completed` `valid` is false | Increase `_GUIDE_VALIDATION_ATTEMPTS` or review section repetition policy |
| Low retrieval hits | `retrieval_stage:scope_retrieval` returns few results | Verify section scope resolution is working; check Qdrant collection populated |
| Slow indexing | `index_stage:embedding_start` → `upsert_completed` is slow | Profile dense embedding model; consider sparse-only fallback |

---

## Payload Size Guidelines

To keep LangSmith traces lightweight and queryable:

- **Text Content:** Never send > 200 chars per trace
- **Lists:** Send counts (int) not full lists; max 3 items if sending list samples
- **Large Objects:** Send summary fields only (e.g., `num_sections` not full hierarchy)
- **Sensitive Data:** Omit PII (author names, dates in document body); OK to send document title/abstract

---

## LangSmith Query Examples

Once traces are flowing, use these LangSmith queries to analyze performance:

```sql
-- Total ingestion time per document
SELECT 
  name, 
  SUM(duration_ms) as total_ms 
FROM runs 
WHERE name LIKE 'ingest_stage:%' 
GROUP BY session_id

-- Metadata extraction failures
SELECT * FROM runs 
WHERE name = 'metadata_stage:extract_failure'
ORDER BY created_at DESC

-- Guide validation retries
SELECT 
  name, 
  count(*) as retry_attempts 
FROM runs 
WHERE name LIKE 'guide_APPLIED_%'
GROUP BY session_id

-- Retrieval recall by section scope
SELECT 
  inputs->>'resolved_sections',
  AVG(CAST(outputs->>'scoped_count' AS INT)) as avg_scoped_hits,
  AVG(CAST(outputs->>'reranked_count' AS INT)) as avg_final_hits
FROM runs
WHERE name = 'retrieval_stage:reranking'
GROUP BY 1
```

---

## Next Steps

1. **Enable LangSmith tracing** in [backend/rag/graph.py](backend/rag/graph.py) (set `LANGSMITH_API_KEY` environment variable)
2. **Run a test ingestion + QA workflow** and observe traces in LangSmith dashboard
3. **Validate trace payloads** — confirm no full text content is being sent
4. **Set up LangSmith alerts** for long-running stages (e.g., Guide LLM > 45 sec)
5. **Iterate on trace sampling** — add/remove detail as needed for monitoring vs performance

