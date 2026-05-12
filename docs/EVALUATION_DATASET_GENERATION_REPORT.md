# Evaluation Dataset Generation Report

## Purpose
This report documents how the evaluation dataset was produced, with specific focus on:
- how the input information package for Claude was created,
- what the generated questions were based on,
- how those questions became the final QA evaluation file.

The process described here reflects the current project artifacts and scripts under backend/evaluation and backend/rag.

## Final Output Files
The dataset generation workflow produced two key artifacts:

1. Context package for QA authoring:
- backend/evaluation/dataset/export_for_annotation.json

2. Final evaluation dataset:
- backend/evaluation/dataset/qa_pairs.json

Current counts from repository artifacts:
- export_for_annotation.json: 21 section-scoped context entries
- qa_pairs.json: 32 finalized QA pairs

## High-Level Pipeline
The generation process has two stages:

1. Build a structured evidence package per paper section/guide step.
2. Use Claude to generate high-quality QA pairs from that evidence package.

In other words:
- the project pipeline first computes section-grounded context,
- Claude then writes question-answer pairs using only that prepared context,
- finalized pairs are saved to qa_pairs.json for retrieval and answer evaluation.

## Stage 1: How Information for Claude Was Created

### 1) Paper Selection and Document Binding
Paper definitions are configured in:
- backend/evaluation/config.py

Each evaluation paper includes:
- paper_id
- paper_type
- document_id (Qdrant/indexed document identifier)
- title

This guarantees all later retrieval is bound to a specific indexed paper and avoids cross-paper leakage.

### 2) Guide-Based Question Intent Extraction
The export process reads guide files from output/<document_id>_guide.json and uses the guide steps as semantic intent anchors.

Guide steps carry:
- step objective,
- section_to_read,
- questions_to_answer,
- figure/table dependency flags.

This is important: the context package is not random chunk dumping. It is built from reading-guide intent, so each exported row corresponds to a planned reading objective.

### 3) Section Resolution and Normalization
Section labels in guide steps are mapped to concrete section_id values through normalization/matching logic in:
- backend/evaluation/export_for_annotation.py
- backend/evaluation/export_for_dataset.py

Matching strategy includes:
- full label match (number + title),
- title-only match,
- numbering match,
- numeric prefix fallback,
- fuzzy containment fallback.

This step converts human-readable guide section labels into retrievable section IDs.

### 4) Section-Scoped Retrieval to Build Evidence
For each resolved section, the exporter retrieves top chunks from that exact section using:
- query = guide_step_title
- section_id = resolved section
- document_id = current paper
- rerank = enabled

Retrieved chunks are packaged with:
- chunk IDs,
- chunk text,
- guide step metadata,
- section metadata.

If needed, figure/table context is also added (when schema/index support exists), so Claude can incorporate visual/table evidence too.

### 5) Export Structure Sent to Annotation/Generation Step
Each row in export_for_annotation.json includes rich fields such as:
- paper_id, paper_type, document_id
- section_id, section_title, resolved_section_title
- guide_step_title, guide_step_description
- guide_questions (from guide step)
- chunks: list of chunk_id + text
- figure_context/table_context and related IDs (if applicable)
- needs_figures, needs_tables

This exported row is the information bundle that was provided to Claude for QA generation.

## Stage 2: Claude-Based QA Pair Generation

Claude was used after Stage 1 to generate final QA records from the prepared evidence bundle.

### What Claude Received
Claude was provided section-scoped, guide-aligned information from export_for_annotation.json, including:
- the intended reading objective (guide step title/description),
- seed questions from guide generation (guide_questions),
- retrieved evidence text chunks with IDs,
- section and paper metadata,
- optional figure/table context.

### What Claude Was Expected to Produce
For each selected context row, Claude generated a finalized QA pair with fields later stored in qa_pairs.json:
- question
- reference_answer
- relevant_chunk_ids
- question_type

Question quality target in this workflow was:
- answerable from provided section evidence,
- specific to paper content (not generic textbook prompts),
- grounded in retrievable chunk IDs,
- suitable for retrieval + answer-quality evaluation.

### Basis of Questions
The generated questions are based on three aligned signals:

1. Guide intent signal:
- questions_to_answer and step objectives from the reading guide define what to ask.

2. Section scope signal:
- each generated question is tied to one section_id context package, encouraging local answerability.

3. Evidence signal:
- chunk text and chunk IDs constrain answer content and support ground-truth chunk annotation.

Because of this design, questions are typically:
- factual: metrics, definitions, model settings, reported results,
- conceptual: why/how interpretations from method or discussion sections,
- comparative: limited but present (small subset).

Current distribution in qa_pairs.json:
- factual: 20
- conceptual: 10
- comparative: 2

## Final Dataset Assembly
The final dataset file backend/evaluation/dataset/qa_pairs.json stores per-question records with:
- paper_id, paper_type, document_id
- section_id, section_title
- question
- reference_answer
- relevant_chunk_ids
- question_type

Current per-paper counts:
- paper_theory: 6
- paper_applied: 9
- paper_survey: 9
- paper_memgpt: 8

## Why This Pipeline Is Reliable for Evaluation

### 1) Groundedness by Construction
Questions are authored from section-scoped retrieved evidence, not from free-form memory. This supports faithful evaluation of both retrieval precision and answer faithfulness.

### 2) Traceability
Every QA pair carries relevant_chunk_ids, so retrieval metrics (P@k, R@k, MRR) can be computed against explicit ground truth.

### 3) Coverage Across Paper Types
The dataset spans theory, applied, survey, and applied-agent papers, which reduces overfitting of evaluation conclusions to one paper genre.

### 4) Guide-Driven Relevance
Using guide-step objectives ensures questions focus on meaningful paper understanding tasks instead of arbitrary trivia.

## Known Practical Constraints During Generation
- Section mapping quality matters heavily. If guide labels resolve to weak sections (for example references-like text), generated QA quality drops.
- Chunk quality matters. Noisy chunks can produce weak or overly broad questions.
- Export quality directly affects Claude output quality. Better section context gives better QA pairs.

## Reproduction Summary
To reproduce the same workflow:

1. Ensure paper entries and document IDs are correct in backend/evaluation/config.py.
2. Ensure guide files exist in output as <document_id>_guide.json.
3. Run export script to create the Claude context package:
- backend/evaluation/export_for_annotation.py
4. Provide export_for_annotation.json rows to Claude for QA generation.
5. Save finalized QA pairs in backend/evaluation/dataset/qa_pairs.json using required schema.
6. Run evaluation scripts (retrieval and answer evaluation) over qa_pairs.json.

## Conclusion
The evaluation dataset was not generated from arbitrary prompting. It was produced through a structured two-stage process:
- first, deterministic extraction of guide-aligned, section-scoped evidence,
- then Claude-based QA authoring grounded in that evidence.

As a result, each QA item in qa_pairs.json is traceable to specific paper sections and chunk IDs, which is exactly what is needed for robust retrieval and answer-quality evaluation.