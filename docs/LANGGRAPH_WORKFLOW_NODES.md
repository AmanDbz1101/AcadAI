# LangGraph Workflow - Complete Node Architecture

## Overview

The Research Paper Assistant now has a fully decomposed LangGraph workflow where every important process is a separate node with explicit input/output contracts through shared state.

---

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        INGESTION & EXTRACTION PHASE                       │
└─────────────────────────────────────────────────────────────────────────┘

    START
      │
      ▼
   ┌─────────────┐
   │   ingest    │  Validates PDF, runs OCR if needed
   │   node      │  Input:  pdf_path, force_ocr
   │             │  Output: document_id, validated_document
   └─────────────┘
      │
      ▼
   ┌──────────────────┐
   │  metadata_       │  Extracts title, abstract, keywords via Groq LLM
   │  extraction      │  Input:  validated_document, document_id
   │  node            │  Output: metadata {title, abstract, keywords, sections}
   └──────────────────┘
      │
      ▼
   ┌──────────────────┐
   │  section_        │  Builds hierarchical section tree
   │  hierarchy       │  Input:  validated_document, document_id
   │  node            │  Output: section_hierarchy {nested tree structure}
   └──────────────────┘
      │
      ▼
   ┌──────────────────┐
   │   db_ingestion   │  Persists extracted data to PostgreSQL
   │   node           │  Input:  document_id, validated_document, metadata
   │                  │  Output: db_paper_id, db_status
   └──────────────────┘
      │
      ▼
   ┌──────────────────┐
   │  extraction_     │  Maps extraction results to state keys needed by
   │  mapping node    │  downstream nodes (ensures backward compatibility)
   │                  │  Input:  All ingestion outputs
   │                  │  Output: title, abstract, sections, full_text, etc.
   └──────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                     CLASSIFICATION & ANALYSIS PHASE                       │
└─────────────────────────────────────────────────────────────────────────┘

      ▼
   ┌──────────────────┐
   │   categorizer    │  Classifies paper as APPLIED/THEORETICAL/SURVEY
   │   node           │  Input:  title, abstract
   │                  │  Output: category, confidence, category_reasoning
   └──────────────────┘
      │
      ├─────────────────────────────────────────┬────────────────┬──────────┐
      │ (conditional routing by category)        │                │          │
      ▼                                          ▼                ▼          ▼
   ┌─────────────┐                      ┌─────────────┐   ┌──────────┐  ┌──────────┐
   │ applied_    │                      │theoretical_ │   │ survey_  │  │retrieve_ │
   │ guide node  │◄─── (or query)       │ guide node  │   │guide node│  │and_qa    │
   └─────────────┘                      └─────────────┘   └──────────┘  │(direct Q)│
      │                                      │                │          └──────────┘
      └──────────────────────────────┬───────┴────────────────┘                │
                                     │ (unless skip_retrieve_and_qa)           │
                                     ▼                                         │
                                  ┌──────────────────┐                         │
                                  │  retrieve_and_qa │  Retrieves chunks,    │
                                  │  node            │  answers questions     │
                                  │                  │  Input:  question_     │
                                  │                  │           section_pairs│
                                  │                  │  Output: qa_results,   │
                                  │                  │          retrieval_    │
                                  │                  │          results       │
                                  └──────────────────┘                        │
                                     │◄────────────────────────────────────────┘

         (optional summarizer path)
           │    OR
           ├──► ┌──────────────┐
           │    │ summarizer   │  Generates paper summary
           │    │ node         │  Input:  title, abstract, sections, category
           │    │              │  Output: summary, key_contributions
           │    └──────────────┘
           │         │
           │         ▼

┌─────────────────────────────────────────────────────────────────────────┐
│                        INDEXING & VECTOR STORAGE PHASE                    │
└─────────────────────────────────────────────────────────────────────────┘

      ▼
   ┌──────────────────┐
   │   chunking node  │  Splits sections into token-aware chunks
   │                  │  with section context
   │                  │  Input:  metadata (sections), document_id
   │                  │  Output: chunks, chunking_status
   └──────────────────┘
      │
      ▼
   ┌──────────────────┐
   │   indexing node  │  Embeds chunks (dense + sparse) and
   │                  │  upserts to Qdrant vector store
   │                  │  Input:  chunks, document_id, pdf_path
   │                  │  Output: indexed_chunks_count, indexing_status
   └──────────────────┘
      │
      ▼
      END
```

---

## Node Specifications

### **1. Ingest Node** (`ingest_node`)

**Purpose:** Validate PDF structure and run OCR if needed.

**Inputs (from state):**
- `pdf_path` (str): Path to PDF file
- `force_ocr` (bool, optional): Force OCR reprocessing even if text already available

**Outputs (to state):**
- `document_id` (str): Unique document identifier
- `validated_document` (ValidatedDocument): PDF structure with pages and text
- `ingest_status` (dict): Metadata about ingestion
  - `page_count` (int): Number of pages
  - `ocr_applied` (bool): Whether OCR was applied

**Error Handling:**
- Sets `ingest_status["error"]` if PDF path not provided or file not found
- Adds to `errors` list if ingestion fails

---

### **2. Metadata Extraction Node** (`metadata_extraction_node`)

**Purpose:** Extract structured metadata using Groq LLM.

**Inputs (from state):**
- `validated_document` (ValidatedDocument): From ingest_node
- `document_id` (str): From ingest_node

**Outputs (to state):**
- `metadata` (dict): Extracted information
  - `title` (str): Paper title
  - `abstract` (str): Paper abstract
  - `keywords` (list[str]): Extracted keywords
  - `sections` (list[dict]): Section hierarchy from content
- `metadata_status` (dict): Processing statistics
  - `processing_time_sec` (float): LLM call latency
  - `fields_found` (list[str]): Which fields were successfully extracted

**Error Handling:**
- Sets `metadata_status["error"]` if extraction fails
- Records LLM errors in `errors` list

---

### **3. Section Hierarchy Node** (`section_hierarchy_node`)

**Purpose:** Build hierarchical section tree from extracted metadata.

**Inputs (from state):**
- `validated_document` (ValidatedDocument): From ingest_node
- `metadata` (dict): From metadata_extraction_node
- `document_id` (str): From ingest_node

**Outputs (to state):**
- `section_hierarchy` (dict): Nested section tree with:
  - Section IDs, titles, levels
  - Parent-child relationships
  - Section numbering (e.g., "1.2.3")
- `hierarchy_status` (dict): Tree statistics
  - `depth` (int): Max nesting depth
  - `root_sections` (int): Number of top-level sections

**Error Handling:**
- Sets `hierarchy_status["error"]` if hierarchy building fails
- Adds errors to `errors` list

---

### **4. DB Ingestion Node** (`db_ingestion_node`)

**Purpose:** Persist all extracted data to PostgreSQL `papers` table.

**Inputs (from state):**
- `document_id` (str): Document identifier
- `validated_document` (ValidatedDocument): PDF structure
- `metadata` (dict): Extracted metadata
- `section_hierarchy` (dict): Section tree
- `pdf_path` (str, optional): Original PDF path for reference

**Outputs (to state):**
- `db_paper_id` (int): Assigned database record ID
- `db_status` (dict): Ingestion metadata
  - `stored` (bool): Whether data was successfully persisted
  - `paper_id` (int): Database record ID

**Error Handling:**
- Sets `db_status["stored"] = False` if ingestion fails
- Records DB errors in `errors` list

---

### **5. Extraction Mapping Node** (`extraction_node` - renamed to extraction_mapping role)

**Purpose:** Map ingestion outputs to state keys expected by downstream nodes.

**Inputs (from state):**
- All outputs from ingest, metadata_extraction, section_hierarchy, db_ingestion nodes

**Outputs (to state):**
- `full_text` (str): Complete document text
- `title` (str): Paper title
- `abstract` (str): Paper abstract
- `sections` (list[dict]): Section metadata
- `hierarchy` (dict): Section hierarchy (alias for section_hierarchy)
- Standard extraction format keys for backward compatibility

**Error Handling:**
- Validates all required fields are present before mapping
- Adds mapping errors to `errors` list

---

### **6. Categorizer Node** (`categorizer_node`)

**Purpose:** Classify paper into APPLIED / THEORETICAL / SURVEY.

**Inputs (from state):**
- `title` (str): Paper title
- `abstract` (str): Paper abstract

**Outputs (to state):**
- `category` (str): One of {APPLIED, THEORETICAL, SURVEY}
- `confidence` (str): One of {HIGH, MEDIUM, LOW}
- `category_reasoning` (str): Explanation for classification

**Error Handling:**
- Sets confidence to LOW if classification fails
- Adds errors to `errors` list

**Routing Decision:**
- Routes to `applied_guide`, `theoretical_guide`, `survey_guide`, `retrieve_and_qa`, or `summarizer` based on category and user inputs

---

### **7-9. Guide Nodes** (`applied_guide_node`, `theoretical_guide_node`, `survey_guide_node`)

**Purpose:** Generate category-specific 3-pass reading guides.

**Inputs (from state):**
- `title`, `abstract`, `sections`, `full_text`, `document_id`
- Category-specific context (figures, tables, visual elements)

**Outputs (to state):**
- `reading_guide` (dict): Three-pass structured guide
- `question_section_pairs` (list[dict]): Per-question section mappings
- `questions_to_answer` (list[str]): Flat list of guide questions
- `sections_to_read` (list[str]): Flat list of relevant sections

**Routing Decision:**
- Routes to `retrieve_and_qa` (normal mode) or `chunking` (guide-only mode)
- Routes to `end` if `guide_only_no_further_processing` flag is set

---

### **10. Retrieve & QA Node** (`retrieve_and_qa_node`)

**Purpose:** Retrieve relevant chunks and generate answers to guide questions.

**Inputs (from state):**
- `question_section_pairs` (list[dict]): Questions to answer
- `document_id` (str): For retrieval scoping
- Optional: `query` (str): Direct user query instead of guide questions

**Sub-process: Indexing**
- Automatically calls RetrievalPipeline.index() if not already indexed

**Outputs (to state):**
- `per_question_results` (list[dict]): Per-question retrieval metadata
- `retrieval_results` (list[dict]): Top retrieved chunks
- `qa_results` (list[dict]): Generated answers with confidence scores
- `retrieval_query` (str): Primary query used for retrieval

**Error Handling:**
- Graceful fallback to extractive answers if LLM call fails
- Rate-limit handling with fallback to heuristic answers
- Records all errors in `errors` list

---

### **11. Summarizer Node** (`summarizer_node`)

**Purpose:** Generate abstractive summary of paper.

**Inputs (from state):**
- `title`, `abstract`, `sections`, `category`

**Outputs (to state):**
- `summary` (str): Abstractive paper summary
- `key_contributions` (list[str]): Extracted key contributions

**Error Handling:**
- Gracefully handles LLM failures
- Adds errors to `errors` list

---

### **12. Chunking Node** (`chunking_node`)

**Purpose:** Split sections into token-aware chunks with section context.

**Inputs (from state):**
- `metadata` (dict): Contains sections with text
- `document_id` (str): Document identifier

**Outputs (to state):**
- `chunks` (list[Chunk]): Section-aware chunks ready for embedding
- `chunking_status` (dict): Statistics
  - `num_chunks` (int): Total chunks produced
  - `avg_chunk_tokens` (float): Average chunk size in tokens

**Error Handling:**
- Returns empty chunks list if no sections available
- Records chunking errors in `errors` list

---

### **13. Indexing Node** (`indexing_node`)

**Purpose:** Embed chunks (dense + sparse) and persist to Qdrant.

**Inputs (from state):**
- `chunks` (list[Chunk]): Chunks to embed
- `document_id` (str): Document identifier
- `pdf_path` (str): For hierarchy file resolution

**Outputs (to state):**
- `indexed_chunks_count` (int): Number of chunks successfully indexed
- `indexing_status` (dict): Processing statistics
  - `embedding_time_sec` (float): Time spent on embedding
  - `chunks_indexed` (int): Total chunks in Qdrant

**Error Handling:**
- Logs warnings if hierarchy file not found but attempts indexing anyway
- Records indexing errors in `errors` list

---

## State Contract

### Minimum Required Input State
```python
{
    "pdf_path": "/path/to/paper.pdf",
    "force_ocr": False,  # optional
}
```

### Full State After Ingestion Phase
```python
{
    "pdf_path": "/path/to/paper.pdf",
    "document_id": "doc-uuid-123",
    "validated_document": ValidatedDocument(...),
    "ingest_status": {...},
    
    "metadata": {
        "title": "Paper Title",
        "abstract": "Abstract text...",
        "keywords": ["keyword1", "keyword2"],
        "sections": [{...}],
    },
    "metadata_status": {...},
    
    "section_hierarchy": {...},
    "hierarchy_status": {...},
    
    "db_paper_id": 42,
    "db_status": {...},
}
```

### Full State After Complete Workflow
```python
{
    # Ingestion outputs
    "document_id": "...",
    "validated_document": "...",
    "db_paper_id": 42,
    
    # Metadata
    "title": "...",
    "abstract": "...",
    "sections": [...],
    "full_text": "...",
    
    # Classification
    "category": "APPLIED",
    "confidence": "HIGH",
    
    # Guide / QA
    "reading_guide": {...},
    "question_section_pairs": [...],
    "qa_results": [...],
    
    # Retrieval
    "retrieval_results": [...],
    
    # Indexing
    "chunks": [...],
    "indexed_chunks_count": 345,
    
    # Status tracking
    "ingest_status": {...},
    "metadata_status": {...},
    "hierarchy_status": {...},
    "chunking_status": {...},
    "indexing_status": {...},
    
    # Error tracking
    "errors": [],
}
```

---

## Execution Flow Examples

### Example 1: Full Workflow with Guide + QA

```
User Input: pdf_path="/path/to/paper.pdf"

Flow:
  ingest 
    → metadata_extraction 
    → section_hierarchy 
    → db_ingestion 
    → extraction_mapping 
    → categorizer (category=APPLIED)
    → applied_guide
    → retrieve_and_qa (with guide questions)
    → chunking
    → indexing
    → END

Output: Guide + QA results + indexed vectors in Qdrant
```

### Example 2: Direct Query (Skip Guide)

```
User Input: 
  pdf_path="/path/to/paper.pdf"
  query="What is the main contribution?"

Flow:
  ingest 
    → metadata_extraction 
    → section_hierarchy 
    → db_ingestion 
    → extraction_mapping 
    → categorizer
    → retrieve_and_qa (with direct query, skip guide routing)
    → chunking
    → indexing
    → END

Output: QA results + indexed vectors
```

### Example 3: Guide-Only Mode

```
User Input: 
  pdf_path="/path/to/paper.pdf"
  skip_retrieve_and_qa=True

Flow:
  ingest 
    → metadata_extraction 
    → section_hierarchy 
    → db_ingestion 
    → extraction_mapping 
    → categorizer
    → applied_guide
    → chunking (skip QA, go straight to indexing)
    → indexing
    → END

Output: Guide only (no answers) + indexed vectors
```

---

## Node Input/Output Summary Table

| Node | Input State Keys | Output State Keys | Purpose |
|------|------------------|-------------------|---------|
| ingest | pdf_path, force_ocr | document_id, validated_document, ingest_status | Validate PDF, OCR if needed |
| metadata_extraction | validated_document, document_id | metadata, metadata_status | Extract title/abstract/keywords |
| section_hierarchy | validated_document, document_id, metadata | section_hierarchy, hierarchy_status | Build section tree |
| db_ingestion | document_id, validated_document, metadata | db_paper_id, db_status | Persist to PostgreSQL |
| extraction_mapping | (all ingestion outputs) | title, abstract, sections, full_text, etc. | Map to downstream format |
| categorizer | title, abstract | category, confidence, category_reasoning | Classify paper type |
| guide (×3) | title, abstract, sections, full_text, document_id | reading_guide, question_section_pairs, questions_to_answer | Generate reading guide |
| retrieve_and_qa | question_section_pairs, document_id, query | per_question_results, retrieval_results, qa_results | Retrieve & answer questions |
| summarizer | title, abstract, sections, category | summary, key_contributions | Generate summary |
| chunking | metadata, document_id | chunks, chunking_status | Split into chunks |
| indexing | chunks, document_id, pdf_path | indexed_chunks_count, indexing_status | Embed & upsert to Qdrant |

---

## Benefits of Node Architecture

1. **Modularity:** Each process is independent and can be debugged separately
2. **Testability:** Node inputs/outputs are explicit and can be mocked
3. **Monitoring:** Each node emits status/timing info visible in LangSmith
4. **Reusability:** Nodes can be combined in different workflows
5. **Error Handling:** Failures are localized; partial results preserved in state
6. **Extensibility:** New nodes can be added without modifying existing ones
7. **Observability:** Complete data flow visible through state mutations

