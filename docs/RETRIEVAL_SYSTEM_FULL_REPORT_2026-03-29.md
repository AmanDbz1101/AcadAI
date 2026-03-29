# Retrieval System Full Report

Date: 2026-03-29
Project: Research Paper Assistant

## 1) End-to-End Retrieval Architecture

The current retrieval stack is a hybrid RAG pipeline with section-aware retrieval and optional multimodal context retrieval for figures and tables.

High-level flow:

1. PDF extraction and structure parsing
2. Section hierarchy construction
3. Dual-level chunking (fine and coarse)
4. Dense embedding + sparse BM25 encoding
5. Hybrid retrieval in Qdrant (dense + sparse with RRF)
6. Cross-encoder reranking (FlashRank)
7. Heuristic filtering and deduplication
8. Top-K context assembly for QA and guide question answering

## 2) Techniques Used Across the System

### 2.1 Extraction and Structure

- Docling-based PDF structure extraction
- Section detection and section hierarchy persistence
- Reference section normalization
- Optional Groq fallback for missing metadata fields

### 2.2 Chunking

- Fine chunking for factual-style queries
- Coarse chunking for conceptual-style queries
- Sliding-window overlap for contextual continuity
- Section-aware payload fields: section title, section id, section path, section path ids, level, parent id

### 2.3 Retrieval

- Hybrid retrieval combining:
	- Dense vector similarity
	- Sparse BM25 scoring
- Qdrant server-side fusion with RRF
- Section-scoped filtering using section path ids
- Optional content-type filtering for figure/table retrieval

### 2.4 Reranking

- FlashRank cross-encoder reranking
- Preserves both retrieval score and rerank score
- Final top-N cutoff applied after reranking

### 2.5 QA Preparation

- Relevance threshold filtering
- Near-duplicate chunk suppression using token-overlap Jaccard similarity
- Reference-section exclusion
- Context stitching with section-aware labels

## 3) Models Used

### 3.1 Retrieval Models

- Dense embedding model: BAAI/bge-small-en-v1.5
- Sparse retrieval model: BM25 custom sparse encoder (per-document fitted)
- Reranker model: ms-marco-MiniLM-L-12-v2 (FlashRank)

### 3.2 LLMs in the Overall System

- Main QA and guide/summarization model: llama-3.3-70b-versatile
- Guide question generation model default: llama-3.3-70b-versatile (overridable by GROQ_QGEN_MODEL)
- Query rewrite model configured: llama-3.1-8b-instant
- Table summarization model: llama-3.1-8b-instant
- Figure multimodal summarization model: meta-llama/llama-4-scout-17b-16e-instruct
- Evaluation judge model: llama-3.3-70b-versatile

## 4) Parameter Values

The following are the active default values from code configuration.

### 4.1 Chunking

- Fine chunk size: 150
- Fine chunk overlap: 30
- Coarse chunk size: 400
- Coarse chunk overlap: 60
- Minimum chunk characters retained: 80

### 4.2 Retrieval and Ranking

- Dense vector size: 384
- Retriever top-K (candidate pool): 20
- RRF K: 60
- Scoped top-K: 8
- Fallback top-K: 4
- Reranker top-N: 12
- QA top-K: 4
- Minimum relevance threshold: 0.35

### 4.3 BM25

- k1: 1.5
- b: 0.75

### 4.4 Guide and Parallel Controls

- Max guide questions: 6
- Max rewrite queries: 3
- Max parallel questions: 6

### 4.5 Query Rewrite Settings

- Enable query rewrite flag: true
- Rewrite model: llama-3.1-8b-instant

Note: In current retrieval graph behavior, query rewrite settings are configured in retrieval config but not actively expanded in the question retrieval loop (current expanded query list remains the base question).

## 5) Vector Store Design (Qdrant)

Collection type: Hybrid retrieval collection with named vectors.

- Dense vector name: dense
- Sparse vector name: sparse

Payload indexes include:

- document_id
- section_title
- section_path
- chunk_level
- content_type
- section_id
- parent_section_id
- section_path_ids

This supports fast exact filtering, text filtering, and hierarchical scoped retrieval.

## 6) Retrieval Heuristics in Runtime

- Question type routing:
	- Factual-prefixed questions route to fine chunks
	- Other questions route to coarse chunks
- Section-scoped pass first, fallback broader retrieval if under-recovered
- Rerank budget: max(reranker_top_n, scoped_top_k + fallback_top_k)
- Near-identical chunk dedupe threshold: Jaccard > 0.7 considered duplicate

## 7) Evaluation Coverage and Methods

Evaluation modules used:

1. Retrieval evaluation
2. Answer evaluation (LLM-as-judge)
3. Context precision evaluation (separate update pass)
4. Ablation study
5. Retrieval diagnosis sweep

Metrics used across evaluations:

- Precision at K
- Recall at K
- MRR
- nDCG (diagnosis sweep)
- Faithfulness (answer quality)
- Answer relevancy (answer quality)
- Context precision (chunk relevance proportion)

## 8) Verified Evaluation Results (From Saved Artifacts)

### 8.1 Retrieval Evaluation Aggregate

Based on 32 evaluated questions.

- Precision@2: 0.578125
- Precision@5: 0.300000
- Recall@3: 0.906250
- Recall@5: 0.937500
- MRR: 0.815094

Interpretation:

- Strong recall profile (most relevant chunks are present by top-5)
- Moderate precision profile (ranking quality still has room to improve)

### 8.2 Answer Quality Evaluation

- Faithfulness: 0.8348837209302326
- Answer relevancy: 0.886046511627907
- Context precision: 0.44761904761904764

Pass thresholds used in evaluation script:

- Faithfulness pass threshold: > 0.70
- Answer relevancy pass threshold: > 0.65

Interpretation:

- Answers are generally grounded and relevant
- Context precision indicates ranking/noise reduction remains a key improvement area

### 8.3 Ablation Results

Configurations compared:

1. Dense Only
2. Dense + BM25 (no reranker)
3. Full System (hybrid + reranker + section scope)

Scores:

- Dense Only: P@3 0.39, P@5 0.26, R@5 0.83, MRR 0.72
- Dense + BM25 (no reranker): P@3 0.41, P@5 0.26, R@5 0.83, MRR 0.77
- Full System: P@3 0.48, P@5 0.30, R@5 0.94, MRR 0.82

Improvement (Full vs Dense Only):

- +0.04 in P@5
- +0.10 in MRR

Interpretation:

- Hybrid sparse+dense and section-aware system behavior clearly improves ranking and recall versus dense-only baseline

### 8.4 Diagnosis Sweep Snapshot

Diagnosis report highlights:

- Largest loss stage identified: query/embedding/index recall issue
- Reranker can help in some settings but can also lose relevant chunks in specific sweeps
- Config sweep confirms parameter sensitivity around top_k and rerank settings

## 9) Paper Coverage in Evaluation Config

Papers currently configured include:

- A theory paper
- Attention Is All You Need (applied)
- A PTM survey paper (survey)
- MemGPT (applied)

This gives multi-category coverage of theory/applied/survey behavior.

## 10) Key Observations and Practical Takeaways

1. System retrieval recall is strong, but precision can be improved further.
2. Answer quality is high on faithfulness and relevancy.
3. Context precision is the most obvious optimization target for next gains.
4. Ablation confirms value from the full hybrid + scoped pipeline over dense-only.
5. Query rewrite settings are configured but currently not actively expanded in the main retrieval loop, so that is a realistic optimization lever.

## 11) Primary Source Files

Architecture and retrieval core:

- backend/rag/retrieval/config.py
- backend/rag/retrieval/pipeline.py
- backend/rag/retrieval/search/hybrid_retriever.py
- backend/rag/retrieval/search/reranker.py
- backend/rag/retrieval/embeddings/dense_encoder.py
- backend/rag/retrieval/embeddings/sparse_encoder.py
- backend/rag/retrieval/indexing/indexer.py
- backend/rag/retrieval/indexing/qdrant_store.py
- backend/rag/retrieval/chunking/section_chunker.py
- backend/rag/graph.py

Evaluation scripts and outputs:

- backend/evaluation/evaluate_retrieval.py
- backend/evaluation/evaluate_answers.py
- backend/evaluation/evaluate_context_precision.py
- backend/evaluation/evaluate_ablation.py
- backend/evaluation/results/retrieval_results.json
- backend/evaluation/results/answer_results.json
- backend/evaluation/results/ablation_results.json
- backend/evaluation/results/retrieval_diagnosis_report.json
- backend/evaluation/results/retrieval_diagnosis_config_sweep.json

