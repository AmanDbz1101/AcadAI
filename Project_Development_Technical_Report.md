# Project Development & Technical Report: AcadAI – A Research Paper Reading Assistant

## 1. Problem Statement & Motivation

Reading research papers is a significant challenge for students and beginners, often due to the density of information and lack of structured guidance. AcadAI was conceived as a website-based assistant to help users systematically read and understand research papers, leveraging the "three-pass method." The goal is to provide stepwise reading guidance, contextual highlights, and section-wise explanations, making academic literature more accessible.

## 2. Initial Plan & Assumptions

The original plan was to:
- Extract text from research paper PDFs.
- Store extracted content as vector embeddings for efficient retrieval.
- Design multiple agents:
  - A "steps generator" agent to create reading steps.
  - A "step explainer" agent to provide explanations and context for each step, retrieving only relevant data from the vector store.
- The main motivation was to minimize LLM token usage by avoiding repeated full-document prompts, thus improving efficiency and cost.

Assumptions:
- Text extraction and vector storage would be fast and accurate enough for interactive use.
- Agentic workflows could be orchestrated efficiently with available open-source tools.

## 3. Approaches Tried & Limitations

### 3.1. Unstructured Library for Text Extraction
- **Local Use:** The `unstructured` library was tested for local PDF parsing. However, it was slow (over a minute per document) and less accurate.
- **API Use:** Switching to the Unstructured API improved speed (20–30 seconds per document) and accuracy, but introduced dependency on external services.

### 3.2. SQL Database for Metadata Storage
- Extracted data was initially stored in a SQL database.
- An agentic workflow was built to extract metadata (title, abstract, sections, difficulty, math-heavy, paper type) from the parsed content.
- This workflow was run locally, but performance and scalability were limited.

### 3.3. Qdrant Vector Store Integration
- Transitioned to using Qdrant for vector storage and retrieval.
- Learned to store and retrieve document chunks and metadata efficiently.
- Developed a new workflow for richer metadata extraction, including counts and IDs for text blocks, images, formulas, and tables in each section.

### 3.4. Docling Library for Fast Extraction
- **Discovery:** Found the `docling` library (v2.0+) as a high-performance alternative for initial PDF parsing.
- **Speed Advantage:** Achieves 5-10 second extraction times compared to 20-30 seconds with Unstructured API.
- **Capabilities:** Extracts markdown text, detects headings with levels and page numbers, counts formulas/tables/figures.
- **Trade-off:** Less comprehensive than Unstructured API but sufficient for initial fast response to users.
- **Integration:** Implemented as part of dual-path processing strategy (fast initial extraction + comprehensive background processing).

## 4. Evolution of Design

- **From Local to API:** Due to performance and accuracy issues, the pipeline moved from local-only processing to leveraging cloud APIs for text extraction.
- **From SQL to Vector DB:** The storage backend evolved from a traditional SQL database to a vector database (Qdrant), enabling semantic search and efficient context retrieval for LLM agents.
- **Agentic Workflow Refinement:** The agentic approach was refined to minimize LLM calls, focusing on stepwise, context-aware guidance rather than monolithic document analysis.
- **Dual-Path Architecture:** Latest evolution introduces a dual-path processing strategy:
  - **Fast Path (Docling):** Provides immediate response with 20-30 second extraction using docling library, basic metadata extraction with Groq LLM classification, and SQL-based deduplication.
  - **Comprehensive Path (Unstructured API):** Background processing for detailed element detection, formula/image analysis, and vector store integration (planned).
  - **Benefit:** Users get instant feedback with fast extraction while comprehensive analysis runs in the background.

## 5. Current Architecture & Implementation

### 5.1. System Overview

- **Frontend:** (Planned) Web UI with three columns:
  - Left: Stepwise reading guide (three-pass method).
  - Center: PDF viewer with highlight and scroll features.
  - Right: Section-wise explanations, summaries, formula and image descriptions.
- **Backend:** FastAPI service for PDF upload and metadata extraction.
- **Pipeline:**
  1. PDF text extraction (Unstructured API).
  2. Section detection (heuristics, no LLM).
  3. Title and abstract extraction.
  4. Section normalization (mapping to canonical names).
  5. LLM inference (single call for paper type, difficulty, math-heavy, focus sections).
  6. Metadata assembly and storage (Qdrant vector store).

### 5.2. Key Modules & Technologies

- **Text Extraction:** `unstructured[pdf]` (API and local, with preference for API).
- **Vector Store:** Qdrant (cloud-hosted, with HuggingFace embeddings).
- **LLM Inference:** Groq API (Llama-3.3-70b-versatile, single call per paper).
- **Backend:** FastAPI (Python), with endpoints for extraction, health, and cleanup.
- **Orchestration:** LangGraph for modular, observable pipeline execution.
- **Data Models:** Pydantic v2 for strict schema enforcement.
- **Formula/Image Analysis:** pix2text-mfr model, TrOCRProcessor, and ONNX for formula detection and explanation.
- **Testing & CLI:** Comprehensive test suite and CLI tools for database and extraction operations.

### 5.3. Fast Extraction Module (Latest Addition)

**Purpose:** Provide immediate user feedback with rapid document processing while maintaining quality.

**Architecture Components:**

1. **Docling Extractor** (`src/fast_extraction/docling_extractor.py`):
   - Parses PDF using docling library (v2.0+)
   - Extracts markdown text, headings with levels/pages
   - Counts formulas, tables, figures, text blocks
   - Returns structured data in 5-10 seconds

2. **Deduplication Database** (`src/fast_extraction/dedup_database.py`):
   - SQLite-based document tracking
   - SHA256 PDF hashing for reliable deduplication
   - Tracks processing status (pending/processing/completed/failed)
   - Stores document IDs, titles, timestamps
   - Enables <1 second cached document retrieval

3. **Simple Metadata Extractor** (`src/fast_extraction/simple_metadata.py`):
   - Groq LLM classification with JSON mode (llama-3.3-70b-versatile)
   - Two-stage prompting:
     - Heading classification: Identifies canonical sections (Introduction, Methods, Results, etc.)
     - Paper inference: Determines type (Empirical/Theoretical/Survey/etc.), difficulty (easy/medium/hard), math-heavy boolean
   - Structured output via Pydantic models with PydanticOutputParser
   - Fallback classification for LLM failures

4. **Fast Extraction Pipeline** (`src/fast_extraction/pipeline.py`):
   - Main orchestrator coordinating all components
   - Checks deduplication before processing
   - Extracts using Docling, classifies with Groq, stores results
   - Integrates with existing guide generation system
   - Returns (document_id, metadata, is_cached) tuple

5. **FastAPI REST API** (`fast_extraction_api.py`):
   - Production-ready REST API with 10 endpoints (port 8001)
   - **Core Endpoints:**
     - `POST /extract` - Upload PDF, returns document_id and metadata
     - `GET /status/{id}` - Check processing status
     - `GET /metadata/{id}` - Download metadata JSON file
     - `GET /guide/{id}` - Download reading guide JSON
     - `GET /documents` - List all documents with filtering
     - `GET /statistics` - System statistics (total docs, by status, avg time)
     - `POST /reprocess/{id}` - Reprocess failed document
     - `DELETE /document/{id}` - Remove document from system
     - `GET /health` - Health check endpoint
     - `GET /` - API information
   - Automatic Swagger/ReDoc documentation at `/docs` and `/redoc`
   - File upload handling with multipart form data
   - Response models with Pydantic validation

**Data Flow:**
```
PDF Upload → SHA256 Hash → Check Database
    |
    ├─ Cached: Load metadata (<1s)
    |
    └─ New: Docling Extract → Groq Classify → Save Metadata → Generate Guide
                (5-10s)           (3-5s)         (1-2s)         (10-15s)
                            Total: 20-30 seconds
```

**Performance Characteristics:**
- First-time extraction: 20-30 seconds end-to-end
- Cached retrieval: <1 second
- Deduplication accuracy: 100% (SHA256-based)
- Concurrent request support via FastAPI async
- Minimal memory footprint (~200MB per document)

## 6. Technologies, Tools, and Frameworks Used

- Python 3.12
- FastAPI
- Unstructured (PDF parsing)
- Qdrant (vector database)
- HuggingFace Transformers (embeddings, formula detection)
- LangGraph (pipeline orchestration)
- Pydantic v2 (data validation)
- Groq API (LLM inference)
- Optimum ONNX (formula detection)
- SQLite (initial storage, now mostly replaced by Qdrant)
- Docker (optional, for deployment)
- Streamlit (planned for frontend)
- dotenv (configuration management)

## 7. Current Progress & Results

- **Backend:** Fully functional FastAPI service for PDF upload and metadata extraction.
- **Extraction Pipeline:** Modular, production-ready, with robust error handling and test coverage.
- **Database:** Qdrant integration for semantic storage and retrieval; legacy SQL support.
- **Formula/Image Analysis:** Working prototype for extracting and explaining formulas from images.
- **Documentation:** Comprehensive technical and user documentation, including architecture, quickstart, and API usage guides.
- **Testing:** All core modules covered by tests; all tests passing.

### 7.1. Fast Extraction Module Results

**Implementation Status:**
- ✅ Complete fast extraction module with 6 Python files (1,400+ lines)
- ✅ SQL deduplication database with SHA256 hashing
- ✅ Groq LLM classification with JSON mode structured outputs
- ✅ Integration with existing guide generation system
- ✅ FastAPI REST API with 10 production-ready endpoints
- ✅ Automated test suite (module + API tests)
- ✅ Comprehensive documentation (7 markdown files)

**Performance Metrics:**
- First-time extraction: 20-30 seconds (MemGPT.pdf: 13.6s, Gated Attention.pdf: 29.8s)
- Cached retrieval: <1 second (measured at 0.0s)
- Deduplication: 100% accuracy, no false positives
- Guide generation: Seamless integration, generates 3-pass reading guides
- API response time: <100ms overhead beyond processing time

**Test Results:**
- Module tests: All passing (MemGPT.pdf and Gated Attention.pdf validated)
- API tests: 9/9 passing including:
  - Health check ✅
  - Statistics endpoint ✅
  - PDF extraction (13.6s) ✅
  - Status retrieval ✅
  - Metadata download ✅
  - Guide generation ✅
  - Document listing ✅
  - Cached extraction (0.0s) ✅
  - Final statistics ✅

**Sample Extraction Results:**

*MemGPT.pdf:*
- Sections: 16 identified (Introduction, Background, MemGPT System, etc.)
- Paper Type: System
- Difficulty: hard
- Math-heavy: false
- Total Pages: 13
- Extraction Time: 13.6s

*Gated Attention for LLMs:*
- Sections: 19 identified (Introduction, Related Work, Method, Experiments, etc.)
- Paper Type: Empirical
- Difficulty: hard
- Math-heavy: true
- Total Pages: 24
- Extraction Time: 29.8s

## 8. Future Work & Improvements

- **Frontend UI:** Complete the web-based interface with interactive PDF viewer and stepwise guide.
- **User Experience:** Add real-time highlights, scroll sync, and richer section explanations.
- **Performance:** Further optimize extraction and retrieval latency, especially for large PDFs.
- **Scalability:** Explore distributed processing and storage for handling larger datasets.
- **Model Improvements:** Experiment with more advanced LLMs and custom fine-tuning for better step explanations.
- **Accessibility:** Add support for more file types and accessibility features for diverse users.

## 9. Key Technical Learnings

- **API vs. Local Processing:** Cloud APIs can offer significant speed and accuracy advantages over local open-source tools, at the cost of external dependencies.
- **Vector Databases:** Qdrant enables efficient semantic search and context retrieval, which is critical for scalable LLM-based applications.
- **Agentic Workflows:** Minimizing LLM calls by designing context-aware, stepwise agents is essential for cost and performance.
- **Modular Pipelines:** Using orchestration frameworks like LangGraph improves maintainability, observability, and extensibility.
- **Schema Enforcement:** Strict data modeling (Pydantic) reduces bugs and ensures consistent outputs across the pipeline.

### 9.1. Fast Extraction Implementation Insights

- **Library Selection Trade-offs:** Choosing between speed (Docling: 5-10s) and comprehensiveness (Unstructured API: 20-30s) depends on use case. Dual-path approach provides best of both worlds.
- **Deduplication Strategy:** SHA256 PDF hashing provides 100% reliable deduplication without false positives, essential for caching system.
- **JSON Mode with Groq:** Using JSON mode with structured outputs (Pydantic + PydanticOutputParser) ensures reliable LLM responses with proper schema validation.
- **Fallback Mechanisms:** Always implement fallback classification for LLM failures to ensure system resilience.
- **Pydantic Best Practices:** Using `Field(default_factory=...)` ensures fields are properly serialized even with default values, critical for downstream systems.
- **API Design:** FastAPI's automatic documentation (Swagger/ReDoc) is invaluable for testing and client integration.
- **Async Processing:** FastAPI's async support enables concurrent request handling without blocking.

### 9.2. Performance Optimization Lessons

- **Caching Strategy:** Database-backed caching with hash-based deduplication reduces repeated processing from 20-30s to <1s.
- **LLM Call Minimization:** Single Groq API call for both heading classification and paper inference (via structured prompts) reduces latency and cost.
- **File I/O Optimization:** Saving metadata to JSON files enables fast retrieval without database queries.
- **Memory Management:** Processing documents in-memory (not storing full text in DB) keeps memory footprint minimal.

### 9.3. Library Comparison: Docling vs Unstructured

| Feature | Docling | Unstructured API |
|---------|---------|------------------|
| Speed | 5-10s | 20-30s |
| Heading Detection | Excellent (with levels) | Good |
| Table Detection | Basic counts | Detailed structure |
| Formula Detection | Basic counts | LaTeX extraction |
| Image Analysis | Basic counts | OCR + descriptions |
| Setup | pip install docling | API key required |
| Cost | Free | $0.01-0.05/page |
| Use Case | Fast initial response | Comprehensive analysis |
| Reliability | High (local) | Depends on API uptime |

### 9.1. Fast Extraction Implementation Insights

- **Library Selection Trade-offs:** Choosing between speed (Docling: 5-10s) and comprehensiveness (Unstructured API: 20-30s) depends on use case. Dual-path approach provides best of both worlds.
- **Deduplication Strategy:** SHA256 PDF hashing provides 100% reliable deduplication without false positives, essential for caching system.
- **JSON Mode with Groq:** Using JSON mode with structured outputs (Pydantic + PydanticOutputParser) ensures reliable LLM responses with proper schema validation.
- **Fallback Mechanisms:** Always implement fallback classification for LLM failures to ensure system resilience.
- **Pydantic Best Practices:** Using `Field(default_factory=...)` ensures fields are properly serialized even with default values, critical for downstream systems.
- **API Design:** FastAPI's automatic documentation (Swagger/ReDoc) is invaluable for testing and client integration.
- **Async Processing:** FastAPI's async support enables concurrent request handling without blocking.

### 9.2. Performance Optimization Lessons

- **Caching Strategy:** Database-backed caching with hash-based deduplication reduces repeated processing from 20-30s to <1s.
- **LLM Call Minimization:** Single Groq API call for both heading classification and paper inference (via structured prompts) reduces latency and cost.
- **File I/O Optimization:** Saving metadata to JSON files enables fast retrieval without database queries.
- **Memory Management:** Processing documents in-memory (not storing full text in DB) keeps memory footprint minimal.

### 9.3. Library Comparison: Docling vs Unstructured

| Feature | Docling | Unstructured API |
|---------|---------|------------------|
| Speed | 5-10s | 20-30s |
| Heading Detection | Excellent (with levels) | Good |
| Table Detection | Basic counts | Detailed structure |
| Formula Detection | Basic counts | LaTeX extraction |
| Image Analysis | Basic counts | OCR + descriptions |
| Setup | pip install docling | API key required |
| Cost | Free | $0.01-0.05/page |
| Use Case | Fast initial response | Comprehensive analysis |
| Reliability | High (local) | Depends on API uptime |

## 10. Production Deployment Readiness

### 10.1. Current Status

**Backend Services:**
- ✅ Main application (app.py) running on default port
- ✅ Fast extraction API (fast_extraction_api.py) running on port 8001
- ✅ Both services tested and validated
- ✅ Comprehensive test suites (9/9 API tests passing)

**Infrastructure:**
- ✅ Virtual environment configured (env_research/)
- ✅ All dependencies installed and tested
- ✅ SQLite database for deduplication
- ✅ File-based storage for uploads/ and output/
- ⚠️ Qdrant vector store (cloud-hosted, credentials configured)

**Monitoring & Logging:**
- ✅ Basic logging configured (logs/ directory)
- ⚠️ No production-grade monitoring yet
- ⚠️ No error tracking/alerting system

### 10.2. Deployment Checklist

**Immediate Priorities:**
- [ ] Configure CORS properly for frontend integration
- [ ] Add rate limiting to prevent abuse
- [ ] Implement request authentication/API keys
- [ ] Set up centralized logging (e.g., ELK stack)
- [ ] Add health check monitoring
- [ ] Configure reverse proxy (Nginx/Apache)
- [ ] Set up SSL/TLS certificates
- [ ] Database backup strategy

**Medium-term Improvements:**
- [ ] Container orchestration (Docker Compose or Kubernetes)
- [ ] Load balancing for high availability
- [ ] Implement background job queue (Celery/RQ) for Unstructured API calls
- [ ] Add Redis for session/cache management
- [ ] Set up CI/CD pipeline
- [ ] Performance monitoring and profiling
- [ ] Automated backup and disaster recovery

**Long-term Enhancements:**
- [ ] Multi-region deployment
- [ ] CDN for static assets
- [ ] Advanced caching strategies
- [ ] A/B testing framework
- [ ] Usage analytics and metrics dashboard

### 10.3. Estimated Timeline for Full Production Deployment

- **Week 1-2:** Frontend development + API integration
- **Week 3:** Security hardening (auth, CORS, rate limiting)
- **Week 4:** Infrastructure setup (Docker, Nginx, SSL)
- **Week 5:** Monitoring and logging implementation
- **Week 6:** Load testing and optimization
- **Week 7-8:** Beta testing with real users
- **Week 9:** Production launch preparation
- **Week 10:** Production deployment and monitoring

---

