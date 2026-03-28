"""Evaluate retrieval performance using manually annotated dataset."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rag.retrieval import RetrievalPipeline  # type: ignore[import-not-found]
from evaluation.config import RESULTS_DIR  # type: ignore[import-not-found]


DATASET_PATH = PROJECT_ROOT / "evaluation/dataset/qa_pairs.json"
RESULTS_OUTPUT = PROJECT_ROOT / RESULTS_DIR / "retrieval_results.json"


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    """Load qa_pairs.json and filter out incomplete entries."""
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found at {path}")

    with path.open("r", encoding="utf-8") as f:
        entries = json.load(f)

    if not isinstance(entries, list):
        raise ValueError("Dataset must be a JSON list")

    filtered = []
    for entry in entries:
        relevant_ids = entry.get("relevant_chunk_ids") or []
        # Skip if contains placeholder text
        if any("FILL IN" in str(rid) for rid in relevant_ids):
            continue
        # Skip if question is placeholder
        if "FILL IN" in entry.get("question", ""):
            continue
        filtered.append(entry)

    return filtered


def _compute_mrr(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """Compute Mean Reciprocal Rank (1/position of first relevant, or 0)."""
    for rank, chunk_id in enumerate(retrieved_ids, 1):
        if chunk_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def _precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Compute precision@k using a fixed k denominator."""
    if k <= 0:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / k if retrieved_ids else 0.0


def _recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Compute recall@k based on overlap with relevant IDs."""
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / len(relevant_ids)


def _evaluate_entry(
    pipeline: RetrievalPipeline,
    entry: dict[str, Any],
    debug_count: int,
) -> tuple[dict[str, Any], int]:
    """Evaluate one question and return metrics."""
    question = entry.get("question", "")
    section_id = entry.get("section_id", "")
    document_id = entry.get("document_id", "")
    relevant_ids = [str(x) for x in entry['relevant_chunk_ids']]

    chunks = pipeline.retrieve_with_section_scope(
        query=question,
        section_id=section_id,
        document_id=document_id,
        top_k=5,
        rerank=True,
    )

    retrieved_ids = []
    for chunk in chunks:
        if hasattr(chunk, 'metadata') and isinstance(chunk.metadata, dict):
            cid = chunk.metadata.get('_id')
            if cid:
                retrieved_ids.append(str(cid))

    if debug_count < 3:
        print(f"\nDEBUG Question: {entry['question'][:60]}")
        print(f"DEBUG relevant_chunk_ids from dataset: {entry['relevant_chunk_ids']}")
        print(f"DEBUG retrieved chunk ids: {retrieved_ids}")
        print(f"DEBUG first result full metadata: {chunks[0].metadata if chunks else 'no results'}")
        debug_count += 1

    relevant_set = set(relevant_ids)

    # Metrics
    precision_at_2 = _precision_at_k(retrieved_ids, relevant_set, 2)
    precision_at_5 = _precision_at_k(retrieved_ids, relevant_set, 5)
    recall_at_3 = _recall_at_k(retrieved_ids, relevant_set, 3)
    recall_at_5 = _recall_at_k(retrieved_ids, relevant_set, 5)
    reciprocal_rank = _compute_mrr(retrieved_ids[:5], relevant_set)

    return {
        "question": question,
        "paper_type": entry.get("paper_type", ""),
        "section_title": entry.get("section_title", ""),
        "question_type": entry.get("question_type", ""),
        "retrieved_ids": retrieved_ids[:5],
        "relevant_ids": list(relevant_ids),
        "precision_at_2": round(precision_at_2, 3),
        "precision_at_5": round(precision_at_5, 3),
        "recall_at_3": round(recall_at_3, 3),
        "recall_at_5": round(recall_at_5, 3),
        "reciprocal_rank": round(reciprocal_rank, 3),
    }, debug_count


def main() -> None:
    print("Loading dataset...")
    entries = _load_dataset(DATASET_PATH)
    if not entries:
        print("No valid entries found in dataset (all incomplete).")
        return

    print(f"Evaluating {len(entries)} questions...")
    pipeline = RetrievalPipeline()

    results = []
    debug_count = 0
    for idx, entry in enumerate(entries, 1):
        result, debug_count = _evaluate_entry(pipeline, entry, debug_count)
        results.append(result)
        if idx % 5 == 0:
            print(f"  {idx}/{len(entries)} evaluated")

    # Compute aggregates
    mean_p2 = sum(r["precision_at_2"] for r in results) / len(results)
    mean_p5 = sum(r["precision_at_5"] for r in results) / len(results)
    mean_recall3 = sum(r["recall_at_3"] for r in results) / len(results)
    mean_recall5 = sum(r["recall_at_5"] for r in results) / len(results)
    mean_mrr = sum(r["reciprocal_rank"] for r in results) / len(results)

    by_paper_type: dict[str, list[dict]] = defaultdict(list)
    by_question_type: dict[str, list[dict]] = defaultdict(list)

    for result in results:
        by_paper_type[result["paper_type"]].append(result)
        by_question_type[result["question_type"]].append(result)

    # Print results
    print("\n" + "=" * 45)
    print("RETRIEVAL EVALUATION RESULTS")
    print("=" * 45)
    print(f"Total questions evaluated: {len(results)}\n")

    print("Overall:")
    print(f"  Mean Precision@2 : {mean_p2:.3f}")
    print(f"  Mean Precision@5 : {mean_p5:.3f}")
    print(f"  Mean Recall@3    : {mean_recall3:.3f}")
    print(f"  Mean Recall@5    : {mean_recall5:.3f}")
    print(f"  Mean MRR         : {mean_mrr:.3f}\n")

    print("By paper type:")
    for paper_type in sorted(by_paper_type.keys()):
        type_results = by_paper_type[paper_type]
        p2 = sum(r["precision_at_2"] for r in type_results) / len(type_results)
        p5 = sum(r["precision_at_5"] for r in type_results) / len(type_results)
        recall3 = sum(r["recall_at_3"] for r in type_results) / len(type_results)
        recall5 = sum(r["recall_at_5"] for r in type_results) / len(type_results)
        mrr = sum(r["reciprocal_rank"] for r in type_results) / len(type_results)
        print(
            f"  {paper_type:10} — P@2: {p2:.2f}  P@5: {p5:.2f}  "
            f"Recall@3: {recall3:.2f}  Recall@5: {recall5:.2f}  MRR: {mrr:.2f}"
        )

    print("\nBy question type:")
    for q_type in sorted(by_question_type.keys()):
        q_results = by_question_type[q_type]
        if q_results:
            p2 = sum(r["precision_at_2"] for r in q_results) / len(q_results)
            p5 = sum(r["precision_at_5"] for r in q_results) / len(q_results)
            recall3 = sum(r["recall_at_3"] for r in q_results) / len(q_results)
            recall5 = sum(r["recall_at_5"] for r in q_results) / len(q_results)
            mrr = sum(r["reciprocal_rank"] for r in q_results) / len(q_results)
            print(
                f"  {q_type:12} — P@2: {p2:.2f}  P@5: {p5:.2f}  "
                f"Recall@3: {recall3:.2f}  Recall@5: {recall5:.2f}  MRR: {mrr:.2f}"
            )

    # Save per-question results
    RESULTS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nPer-question results saved to: {RESULTS_OUTPUT}")


if __name__ == "__main__":
    main()
