# Session Changelog - 2026-03-22

## Scope
Removed the query-optimizer rewrite path used before retrieval and documented behavior changes.

## Changes Made

### 1. Removed query rewrite prompt path from retrieval flow
- File changed: `backend/rag/graph.py`
- Removed `_rewrite_query_candidates(...)`, which previously generated 2-3 rewritten retrieval queries via LLM.
- Removed the prompt block that started with:
  - `You optimize search queries for research paper retrieval.`
  - JSON schema: `{"queries": ["...", "..."]}`
  - Rules for keyword-dense short queries.
- Updated `_retrieve_for_question(...)` to use only the original question text for retrieval.

### 2. Simplified retrieval behavior
- Retrieval now executes scoped + fallback searches with a single query (`question.strip()`).
- Existing section-aware filtering, deduplication, reranking, and QA generation are unchanged.

### 3. Cleaned related graph wiring/comments
- Updated retrieval flow docstrings to reflect removal of rewrite step.
- Removed now-unused `_retrieve_for_question(..., category=...)` parameter.

## Impact
- Removed one LLM call per question from the retrieval path.
- Reduced latency and failure surface related to rewrite-model limits/failures.
- Retrieval is now deterministic with respect to user/guide question wording.

## Notes
- Retrieval config entries related to query rewrite may still exist in config files for backward compatibility, but they are no longer used by `backend/rag/graph.py`.
