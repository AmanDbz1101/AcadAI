# Retrieval Pipeline Visualization with LangSmith

This guide shows how to visualize retrieval chunk flow from query to final output.

## What is traced

The retrieval pipeline now emits stage-specific LangSmith runs with chunk counts.
Each child run is named as `retrieval_stage:<stage_name>`:

- `candidate_retrieval`
- `rerank` or `rerank_skipped`
- `final_output`
- `section_scoped_candidate_retrieval`
- `section_scoped_final_output`

The chatbot flow also emits graph-level retrieval stages.
Each child run is named as `chat_retrieval_stage:<stage_name>`:

- `scoped_retrieval`
- `scoped_dedup`
- `fallback_retrieval` (when scoped recall is low)
- `fallback_merged_dedup`
- `compatibility_retrieval` (legacy index fallback path)
- `compatibility_dedup`
- `rerank_input`
- `rerank_output`
- `chat_answer_input` (the exact chunks passed into QA answer generation)

Each stage includes counts such as:

- `top_k_requested`
- `top_n_requested`
- `candidate_count`
- `reranked_count`
- `returned_count`
- `cutoff_count`
- `using_bm25`

And now includes chunk previews for quick inspection:

- `candidate_chunks`
- `input_chunks`
- `output_chunks`
- `returned_chunks`

Each chunk preview contains:

- `chunk_id`
- `score`
- `section_id`
- `section_title`
- `content_type`
- `chunk_level`
- `content_preview`

## How chunk flow works

For a typical call:

1. Candidate retrieval fetches up to `top_k` chunks from hybrid search.
2. Reranker scores candidates and returns the top `top_n`.
3. Final output is what downstream QA/answering consumes.

Cutoff is:

- `cutoff_count = candidate_count - returned_count`

## Enable LangSmith

Set environment variables before running backend or evaluation scripts:

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your_langsmith_api_key>
export LANGCHAIN_PROJECT=ResearchPaperAssistant
# optional
export LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

## Run examples

General retrieval evaluation:

```bash
python backend/evaluation/evaluate_retrieval.py
```

Ablation retrieval evaluation:

```bash
python backend/evaluation/evaluate_ablation.py
```

## What to inspect in LangSmith UI

For each query run, inspect child runs and compare:

1. `retrieval_stage:candidate_retrieval` `candidate_count` vs `retrieval_stage:final_output` `returned_count`
2. `retrieval_stage:rerank` `input_count` vs `output_count`
3. `cutoff_count` after rerank
4. `using_bm25` (true means hybrid retrieval, false means dense-only fallback)
5. `chat_retrieval_stage:*` runs for scoped/fallback/dedup behavior
6. `candidate_chunks` and `returned_chunks` content previews to verify relevance

Tip:

- The trace payload stores up to 8 chunks per stage with content preview truncated to keep runs readable.

## Interpreting reranker impact

Reranker helps when:

- `candidate_count` is high
- final `returned_count` is much smaller
- quality metrics (MRR, precision) improve while cutoff increases

This means the system retrieves broadly, then keeps only the most relevant chunks.
