# Research Paper Assistant Report Outline and Writeup Guide

This document is a project-specific guide for writing the final report or technical thesis for the Research Paper Assistant system.

The outline below is based on the actual codebase, especially the project README, the backend workflow, and the LangGraph node architecture. It is written so you can use it directly as a report structure and also understand what each section must contain.

## Suggested Contents

1. Page of Approval
2. Copyright
3. Acknowledgements
4. Abstract
5. Contents
6. List of Figures
7. List of Tables
8. List of Abbreviations
9. Chapter 1: Introduction
10. Chapter 2: Literature Review
11. Chapter 3: Requirements and Methodology
12. Chapter 4: System Design
13. Chapter 5: Implementation
14. Chapter 6: Testing and Evaluation
15. Chapter 7: Results and Discussion
16. Chapter 8: Conclusion and Future Work
17. References
18. Appendices

## 1. Front Matter

### Page of Approval
What to include:
- Project title
- Student name and ID
- Supervisor name
- Department, faculty, and university
- Submission date
- Approval signatures

### Copyright
What to include:
- Short copyright declaration
- Ownership statement for the project report
- Year and author name

### Acknowledgements
What to include:
- Supervisor and advisor thanks
- Lab, department, and institution support
- Anyone who contributed data, guidance, or testing support

### Abstract
What to include:
- 1 paragraph summary of the whole project
- The problem: research papers are large and hard to analyze manually
- The solution: a system that extracts PDFs, identifies structure, stores results, and supports guided reading and QA
- Main modules: PDF ingestion, metadata extraction, section hierarchy, PostgreSQL storage, retrieval pipeline, React frontend
- Key result or outcome
- Optional mention of technologies used: FastAPI, React, LangGraph, PostgreSQL, Qdrant, Docling

### Contents
What to include:
- Auto-generated table of contents
- All chapters, subsections, figures, tables, and appendices with page numbers

### List of Figures
What to include:
- All figures with exact captions
- Use the same numbering as in the report

### List of Tables
What to include:
- All tables with exact captions
- Keep numbering consistent with chapter numbering

### List of Abbreviations
What to include:
- All short forms used in the report
- Example entries:
  - PDF: Portable Document Format
  - OCR: Optical Character Recognition
  - NLP: Natural Language Processing
  - LLM: Large Language Model
  - API: Application Programming Interface
  - DB: Database
  - UI: User Interface
  - QA: Question Answering
  - RAG: Retrieval-Augmented Generation
  - ORM: Object-Relational Mapping
  - SPA: Single Page Application

## 2. Chapter 1: Introduction

### 1.1 Background
What to include:
- Explain why research papers are difficult to read and process manually
- Mention the size, structure, and technical density of papers
- Explain the need for a tool that can extract, organize, and summarize content automatically

### 1.2 Problem Statement
What to include:
- State the exact problem your system solves
- Example: extracting useful information from research PDFs is time-consuming and inconsistent when done manually
- Mention issues such as unstructured PDFs, scanned documents, hidden section hierarchy, and slow searching

### 1.3 Objectives
What to include:
- Build a system to ingest research PDFs
- Extract metadata and section structure
- Store extracted results in a database
- Support retrieval and question answering over the paper content
- Provide a web interface for browsing papers and extracted insights

### 1.4 Scope
What to include:
- What the system does now
- What types of PDFs are supported
- What outputs are generated
- What is outside scope, such as full scientific fact verification or multi-paper synthesis unless implemented

### 1.5 Importance of the Project
What to include:
- Why this system is useful for researchers and students
- How it reduces reading effort and speeds up review
- How it can support literature review, paper comprehension, and document exploration

### 1.6 Chapter Summary
What to include:
- A short summary of the rest of the report structure

## 3. Chapter 2: Literature Review

### 2.1 Research Paper Analysis Tools
What to include:
- Existing PDF readers, document parsers, and research assistants
- Compare manual reading vs automated analysis systems

### 2.2 PDF Extraction and OCR
What to include:
- Explain how PDF parsing works
- Discuss text-based PDFs versus scanned PDFs
- Mention OCR as a fallback for low-text-density pages

### 2.3 Metadata Extraction
What to include:
- Review methods for extracting title, authors, abstract, keywords, DOI, and affiliations
- Mention heuristic extraction and LLM-assisted extraction

### 2.4 Section Detection and Hierarchy Extraction
What to include:
- Explain why section hierarchy matters for reading and chunking
- Discuss section segmentation, numbering, and tree structures

### 2.5 Retrieval-Augmented Generation and Question Answering
What to include:
- Explain embeddings, vector search, chunk retrieval, reranking, and answer generation
- Mention why RAG is useful for long documents

### 2.6 Workflow Orchestration and LangGraph
What to include:
- Explain workflow graphs and state-based orchestration
- Mention multi-step pipelines for ingestion, classification, indexing, and QA

### 2.7 Gap Analysis
What to include:
- State what existing tools do well and what they miss
- Explain the gap your project addresses: end-to-end handling of a paper from upload to structured browsing and QA

### 2.8 Chapter Summary
What to include:
- Short recap of the technologies and ideas that motivated your design

## 4. Chapter 3: Requirements and Methodology

### 3.1 Functional Requirements
What to include:
- PDF upload and validation
- Metadata extraction
- Section hierarchy generation
- Extraction persistence to database
- Paper browsing in the frontend
- Question answering or guided reading support
- Retrieval and indexing of content for search

### 3.2 Non-Functional Requirements
What to include:
- Accuracy
- Processing speed
- Reliability
- Maintainability
- Scalability
- Usability

### 3.3 Tools and Technologies
What to include:
- FastAPI
- React and Vite
- PostgreSQL
- Docling
- LangGraph and LangChain components
- Qdrant or other retrieval components used in the backend

### 3.4 Methodology
What to include:
- Explain the pipeline in order:
  1. Validate PDF
  2. Load and extract text/layout
  3. Apply OCR when needed
  4. Extract metadata
  5. Build section hierarchy
  6. Store structured data
  7. Chunk and index content
  8. Retrieve and answer user questions

### 3.5 Development Approach
What to include:
- Whether the project was built in phases or modules
- Why an iterative architecture was used
- How backend and frontend development were coordinated

### 3.6 Chapter Summary
What to include:
- Brief summary of requirements and working method

## 5. Chapter 4: System Design

### 4.1 Overall Architecture
What to include:
- Show the end-to-end architecture
- Present the main layers:
  - Presentation layer: React frontend
  - API layer: FastAPI backend
  - Processing layer: extraction and LangGraph workflow
  - Storage layer: PostgreSQL and vector store

### 4.2 Module Design
What to include:
- PDF ingestion pipeline
- Metadata extraction pipeline
- Section hierarchy pipeline
- Database ingestion and persistence
- Retrieval and QA workflow
- Frontend paper browsing and AI tools panel

### 4.3 Data Flow Design
What to include:
- Show how data moves from PDF upload to extracted document objects, stored records, retrieval chunks, and UI rendering
- Mention the key outputs at each stage

### 4.4 Database Design
What to include:
- Main entities and relationships
- Papers, sections, text blocks, figures, tables, and document records
- Explain normalization or document-oriented storage choices

### 4.5 Diagram Set
What to include:
- Use case diagram
- Block diagram
- Sequence diagram
- Activity diagram
- Optional workflow diagram for LangGraph nodes

### 4.6 Chapter Summary
What to include:
- A concise wrap-up of the design decisions

## 6. Chapter 5: Implementation

### 5.1 Backend Setup
What to include:
- Project structure
- Environment configuration
- Main backend entry points
- Dependencies and package organization

### 5.2 PDF Ingestion Module
What to include:
- Validation logic
- PDF loading
- OCR fallback
- Document object creation
- Error handling and deduplication

### 5.3 Metadata Extraction Module
What to include:
- How title, abstract, keywords, and related fields are extracted
- Whether rules, heuristics, or LLM fallback are used
- What the output data structure looks like

### 5.4 Section Hierarchy Module
What to include:
- How section titles are detected
- How numbering and parent-child relationships are built
- How the section tree is represented

### 5.5 Database Persistence
What to include:
- How extracted data is inserted into PostgreSQL
- How duplicates are handled
- How documents, sections, and blocks are stored

### 5.6 Retrieval and LangGraph Workflow
What to include:
- Explain the workflow nodes
- Ingest node
- Metadata extraction node
- Section hierarchy node
- DB ingestion node
- Categorizer node
- Guide nodes and retrieve-and-QA node
- Summarizer node if used

### 5.7 Frontend Implementation
What to include:
- Main UI layout
- Paper navigation panel
- Paper viewer panel
- AI tools or insights panel
- API integration with the backend

### 5.8 Technical-Term Detector or Extra Module
What to include:
- Only if this module is part of your final project
- Purpose of the subsystem
- Input/output behavior
- How it integrates with the main system

### 5.9 Chapter Summary
What to include:
- Brief explanation of what was implemented and how the modules fit together

## 7. Chapter 6: Testing and Evaluation

### 6.1 Testing Strategy
What to include:
- Unit testing
- Integration testing
- Manual testing
- Any pipeline or end-to-end smoke tests

### 6.2 Test Cases
What to include:
- Validation of valid and invalid PDFs
- Corrupted and encrypted PDF handling
- Text extraction correctness
- Section hierarchy correctness
- Database persistence checks
- Retrieval and QA checks

### 6.3 Evaluation Metrics
What to include:
- Extraction accuracy
- Coverage of metadata fields
- Hierarchy quality
- Retrieval relevance
- Response usefulness
- Processing time

### 6.4 Error Analysis
What to include:
- What kinds of documents fail or degrade performance
- Scanned PDFs
- Tables and figures with noisy layouts
- Section numbering inconsistencies

### 6.5 Chapter Summary
What to include:
- State the overall testing outcome and whether the system satisfies requirements

## 8. Chapter 7: Results and Discussion

### 7.1 Extraction Results
What to include:
- Example output from a PDF upload
- Extracted title, abstract, sections, and metadata
- Any screenshots of extracted data

### 7.2 Hierarchy and Structure Results
What to include:
- Show how section trees are generated
- Explain how chapter/subchapter relationships are represented

### 7.3 Retrieval and QA Results
What to include:
- Examples of user questions and answers
- Retrieved supporting sections or chunks
- Any evidence that the workflow improves answer quality

### 7.4 Frontend Results
What to include:
- Screenshots of the web interface
- Paper list
- Document viewer
- Insight panels

### 7.5 Discussion
What to include:
- What worked best
- What limitations remain
- Why certain design choices were necessary

### 7.6 Chapter Summary
What to include:
- One short paragraph that states the main result of the system

## 9. Chapter 8: Conclusion and Future Work

### 8.1 Conclusion
What to include:
- Restate the problem and the final solution
- Summarize the major achievements of the project
- Emphasize the value of the system for researchers and students

### 8.2 Limitations
What to include:
- Cases where the system is weak
- OCR-heavy papers
- Poorly formatted PDFs
- Limited cross-document reasoning if not implemented

### 8.3 Future Work
What to include:
- Better OCR and layout handling
- More robust metadata extraction
- Better retrieval ranking
- Improved QA evaluation
- Support for more document types or multilingual papers
- Better analytics and visualization

## 10. References

What to include:
- All academic papers cited in the literature review
- All libraries, frameworks, and external tools referenced in the implementation
- Keep citation format consistent throughout the report

## 11. Appendices

What to include:
- API endpoint details
- Database schema excerpts
- Example JSON outputs
- Extra figures and screenshots
- Large workflow diagrams
- Configuration examples
- Test result summaries

## Recommended chapter flow for this project

If you want the report to feel natural and technical, use this story:

1. Introduce the pain point of reading research papers manually.
2. Review the methods needed to solve it: parsing, OCR, metadata extraction, hierarchy building, retrieval, and QA.
3. Explain your requirements and the modular pipeline you built.
4. Present the architecture and design diagrams.
5. Describe the implementation module by module.
6. Prove the system with tests and evaluation.
7. Show real outputs and discuss strengths and weaknesses.
8. Close with a conclusion and realistic future work.

## Project-specific points you should mention somewhere in the report

- The backend uses FastAPI and Python for the API and processing logic.
- The frontend uses React and Vite for the interface.
- The system extracts metadata and section hierarchy from research PDFs.
- The project stores extracted content in PostgreSQL.
- The retrieval workflow uses LangGraph-style nodes for orchestration.
- The system supports guided reading and question answering over paper content.
- The codebase includes separate modules for extraction, retrieval, and UI presentation.

## Short writing tip

For each subsection, write in this order:

1. What the problem or component is.
2. Why it is needed.
3. How your project handles it.
4. What output it produces.
5. Any limitation or observation.

That pattern keeps the report consistent and technical without becoming repetitive.
