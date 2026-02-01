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

## 4. Evolution of Design

- **From Local to API:** Due to performance and accuracy issues, the pipeline moved from local-only processing to leveraging cloud APIs for text extraction.
- **From SQL to Vector DB:** The storage backend evolved from a traditional SQL database to a vector database (Qdrant), enabling semantic search and efficient context retrieval for LLM agents.
- **Agentic Workflow Refinement:** The agentic approach was refined to minimize LLM calls, focusing on stepwise, context-aware guidance rather than monolithic document analysis.

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

---

