# Retrieval Trace Step-by-Step (LangSmith)

This note explains the retrieval trace sequence you are seeing in LangSmith, why some stages repeat, why chunk counts differ between passes, and how to interpret retrieval vs rerank scores.

## Why many stages show 0.00s

Most trace nodes are lightweight snapshot events emitted after/between core operations.
They are not full wrappers around the expensive calls themselves, so durations are often rounded to 0.00s in the UI.

## Stage-by-stage flow for one question

Typical observed sequence:

1. `retrieval_stage:candidate_retrieval`
2. `retrieval_stage:final_output`
3. `chat_retrieval_stage:scoped_retrieval`
4. `chat_retrieval_stage:scoped_dedup`
5. `retrieval_stage:candidate_retrieval`
6. `retrieval_stage:final_output`
7. `chat_retrieval_stage:fallback_retrieval`
8. `chat_retrieval_stage:fallback_merged_dedup`
9. `chat_retrieval_stage:rerank_input`
10. `retrieval_stage:rerank`
11. `chat_retrieval_stage:rerank_output`

### What each stage means

- `retrieval_stage:candidate_retrieval`
  - A retrieval pipeline call that fetches candidates (hybrid dense+sparse when available).
- `retrieval_stage:final_output`
  - Output of that same retrieval call after optional cutoff/rerank choice for that call.
- `chat_retrieval_stage:scoped_retrieval`
  - Chat-level summary of retrieval constrained to resolved section scope.
- `chat_retrieval_stage:scoped_dedup`
  - Deduplicates scoped hits.
- `chat_retrieval_stage:fallback_retrieval`
  - Runs broader retrieval when scoped recall is low.
- `chat_retrieval_stage:fallback_merged_dedup`
  - Merges scoped + fallback results, then deduplicates.
- `chat_retrieval_stage:rerank_input`
  - Candidate list that will be sent into reranker.
- `retrieval_stage:rerank`
  - Cross-encoder reranking; includes per-chunk score transitions.
- `chat_retrieval_stage:rerank_output`
  - Final reranked chunk set used by the answering step.

## Why there are 2 candidate retrieval stages

There are two retrieval passes:

- Pass 1: scoped retrieval (section-aware, stricter filter)
- Pass 2: fallback retrieval (broader search) if scoped results under-recover

Fallback triggers when deduplicated scoped hits are fewer than 3.

## Why one pass shows 2 chunks and another shows 4 chunks

This is expected with current defaults:

- `SCOPED_TOP_K = 8` (scoped, stricter filters)
- `FALLBACK_TOP_K = 4` (broader fallback pass)

So you can get:

- Scoped pass: only 2 chunks survive strict scope/filtering
- Fallback pass: up to 4 broader chunks retrieved

Then both sets are merged and deduplicated before reranking.

## Score semantics

### Retrieval score vs rerank score

- `retrieval_score` comes from retrieval stage scoring.
- `rerank_score` comes from cross-encoder reranker.
- They are from different scoring systems/scales.

### Score delta

In trace payload:

`score_delta = rerank_score - retrieval_score`

Example:

- retrieval_score = 1.0
- rerank_score = 0.9993802309036255
- score_delta = -0.0006197690963745117

This only indicates numeric difference between two scoring systems, not necessarily quality gain/loss by itself.
Rank movement (`rank_before` and `rank_after`) is usually more meaningful.

### Why score and rerank_score are equal in rerank output

Expected behavior:

- After reranking, primary `score` is set to rerank score.
- `retrieval_score` is preserved as metadata.
- Therefore, in rerank output you normally see:
  - `score == rerank_score`
  - `retrieval_score` remains the pre-rerank score

## Metadata fields with null values

Trace chunk previews now omit fields whose values are null.
So fields such as `chunk_level`, `content_type`, `section_id`, and `section_title` are shown only when present.

## New trace payload additions

To make score transitions explicit, rerank traces now include:

- `input_chunks`
- `output_chunks`
- `score_transitions` with per-chunk:
  - `chunk_id`
  - `rank_before`
  - `rank_after`
  - `retrieval_score`
  - `rerank_score`
  - `score_delta`
  - `content_preview`
