# Ablation Zero-Metrics Fix

## Problem

`backend/evaluation/evaluate_ablation.py` was reporting `0.00` for all configurations (`Dense Only`, `Dense + BM25`, `Full System`) on both `P@5` and `MRR`.

## Root Cause

The ablation evaluator extracted retrieved IDs from `metadata["chunk_id"]`, but retrieval results in this codebase expose the point identifier as `metadata["_id"]`.

Because of that mismatch, `retrieved_ids` was empty for nearly every question, forcing:

- `precision_at_5 = 0.0`
- `reciprocal_rank = 0.0`

for all configurations.

## Code Change

File updated: `backend/evaluation/evaluate_ablation.py`

Before:

```python
chunk_id = metadata.get("chunk_id", "")
if chunk_id:
    retrieved_ids.append(chunk_id)
```

After:

```python
retrieved_id = metadata.get("_id") or metadata.get("chunk_id") or ""
if retrieved_id:
    retrieved_ids.append(str(retrieved_id))
```

This keeps compatibility with both metadata shapes.

## Validation

Re-ran:

```bash
python backend/evaluation/evaluate_ablation.py
```

Observed non-zero metrics:

- Dense Only: `P@5 = 0.26`, `MRR = 0.72`
- Dense + BM25 (no reranker): `P@5 = 0.26`, `MRR = 0.76`
- Full System: `P@5 = 0.29`, `MRR = 0.82`

Improvement baseline -> full:

- `+0.03` in `P@5`
- `+0.10` in `MRR`

## Notes

- This fix only changes evaluation ID extraction.
- Retrieval/indexing logic was already returning valid results.
- The ablation output is saved at `backend/evaluation/results/ablation_results.json`.
