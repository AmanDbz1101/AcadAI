# Retrieval Evaluation — Design Notes

This sub-package will hold all tooling for offline evaluation of the hybrid
retrieval pipeline.  It is scaffolded but **not yet implemented**; evaluation
will be added as a separate task once the retrieval pipeline is validated
end-to-end.

---

## Planned Metrics

| Metric | Description |
|--------|-------------|
| **Hit Rate @ k** | Fraction of queries where ≥ 1 relevant chunk appears in the top-k results |
| **MRR @ k** | Mean Reciprocal Rank — rewards retrieving the first relevant chunk earlier |
| **NDCG @ k** | Normalised Discounted Cumulative Gain — graded relevance, position-aware |
| **Context Precision** | Of the retrieved chunks, what fraction are actually relevant? |
| **Context Recall** | Of all relevant chunks, what fraction were retrieved? |

---

## Planned Eval Dataset Format

Each row in an evaluation dataset JSON file:

```jsonc
{
  "query_id": "q001",
  "query": "How does multi-head attention work?",
  "document_id": "2a6dfe63-49db-45f5-94d5-135e8fabe1c0",
  "relevant_chunk_ids": ["<chunk_id_1>", "<chunk_id_2>"],
  // optional: graded relevance (0 = not relevant, 1 = partial, 2 = highly relevant)
  "relevance_grades": {"<chunk_id_1>": 2, "<chunk_id_2>": 1}
}
```

---

## Planned Module Structure

```
evaluation/
    __init__.py
    metrics.py          ← hit_rate_at_k, mrr_at_k, ndcg_at_k,
                           context_precision, context_recall
    dataset.py          ← EvalQuery, EvalDataset (load/save JSON)
    evaluator.py        ← eval_retriever(pipeline, dataset, k) → EvalReport
    report.py           ← EvalReport: per-query results + aggregate stats
```

---

## Planned Evaluator Interface

```python
from rag.retrieval.evaluation.evaluator import eval_retriever
from rag.retrieval.evaluation.dataset import EvalDataset
from rag.retrieval import RetrievalPipeline

dataset = EvalDataset.from_json("eval/retrieval_eval.json")
pipeline = RetrievalPipeline()

report = eval_retriever(
    pipeline=pipeline,
    dataset=dataset,
    k=5,
    metrics=["hit_rate", "mrr", "ndcg", "context_precision", "context_recall"],
)

print(report.summary())
report.to_csv("eval/results.csv")
```

---

## Notes

- Eval dataset construction: use LLM-generated question-answer pairs from
  known paper sections, or manual annotation.
- Chunk IDs in the dataset can be obtained by running the indexer and
  inspecting the Qdrant payload (`chunk_id` field).
- Evaluation should be run offline (not in the LangGraph pipeline) to avoid
  latency in production.
