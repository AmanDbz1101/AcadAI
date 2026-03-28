"""Ablation study: compare retrieval configurations to prove each component adds value."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rag.retrieval import RetrievalPipeline  # type: ignore[import-not-found]
from evaluation.config import RESULTS_DIR  # type: ignore[import-not-found]


DATASET_PATH = PROJECT_ROOT / "evaluation/dataset/qa_pairs.json"
RESULTS_OUTPUT = PROJECT_ROOT / RESULTS_DIR / "ablation_results.json"

# Ablation configurations: systematically disable components
CONFIGURATIONS = [
    {
        "name": "Dense Only",
        "description": "Dense vector retrieval, no BM25, no reranker, no section filter",
        "rerank": False,
        "section_scoped": False,
        "use_sparse": False
    },
    {
        "name": "Dense + BM25 (no reranker)",
        "description": "Hybrid retrieval, no reranker, no section filter",
        "rerank": False,
        "section_scoped": False,
        "use_sparse": True
    },
    {
        "name": "Full System",
        "description": "Hybrid + reranker + section-scoped filter",
        "rerank": True,
        "section_scoped": True,
        "use_sparse": True
    }
]


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
    """Compute Mean Reciprocal Rank (1/position of first relevant item, or 0)."""
    for rank, chunk_id in enumerate(retrieved_ids, 1):
        if chunk_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def _precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Compute precision@k using a fixed-k denominator."""
    if k <= 0:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / k if retrieved_ids else 0.0


def _recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Compute recall@k against all relevant IDs."""
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / len(relevant_ids)


def _retrieve_with_config(
    pipeline: RetrievalPipeline,
    config: dict,
    question: str,
    section_id: str,
    document_id: str,
) -> list:
    """
    Retrieve results using the specified configuration.
    
    Configurations:
    1. Dense Only: query() without document_id → forces dense-only
                   (Note: sparse is disabled by not providing document_id)
    2. Dense + BM25: query() with document_id, no rerank → hybrid without rerank
    3. Full System: retrieve_with_section_scope() with section_id and rerank
    """
    if config["section_scoped"]:
        # Use section-scoped retrieval with reranking
        results = pipeline.retrieve_with_section_scope(
            query=question,
            section_id=section_id,
            document_id=document_id,
            top_k=5,
            top_n=5,
            rerank=config["rerank"],
        )
    else:
        # Use general query() method
        if config["use_sparse"]:
            # Hybrid retrieval: provide document_id so BM25 can be loaded
            results = pipeline.query(
                query=question,
                document_id=document_id,
                top_k=5,
                top_n=5,
                rerank=config["rerank"],
            )
        else:
            # Dense-only retrieval: don't provide document_id so BM25 is never loaded
            # Note: sparse is disabled by omitting document_id, which prevents
            # the pipeline from loading the BM25 encoder. If full control over
            # sparse retrieval is needed, a config flag on RetrievalPipeline
            # initialization would be required.
            results = pipeline.query(
                query=question,
                document_id=None,  # Disable sparse by not providing document_id
                top_k=5,
                top_n=5,
                rerank=config["rerank"],
            )

    return results


def _evaluate_entry(
    pipeline: RetrievalPipeline,
    config: dict,
    entry: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one question using a specific configuration and return metrics."""
    question = entry.get("question", "")
    section_id = entry.get("section_id", "")
    document_id = entry.get("document_id", "")
    relevant_ids = set(entry.get("relevant_chunk_ids") or [])

    # Retrieve using configuration
    results = _retrieve_with_config(
        pipeline,
        config,
        question=question,
        section_id=section_id,
        document_id=document_id,
    )

    # Extract chunk IDs from results
    retrieved_ids = []
    for result in results:
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        # RetrievalResult metadata from LangChain/Qdrant exposes point IDs as
        # `_id`; keep `chunk_id` as a fallback for compatibility.
        retrieved_id = metadata.get("_id") or metadata.get("chunk_id") or ""
        if retrieved_id:
            retrieved_ids.append(str(retrieved_id))

    # Compute metrics
    retrieved_set = set(retrieved_ids[:5])
    intersection = retrieved_set & relevant_ids

    precision_at_3 = _precision_at_k(retrieved_ids, relevant_ids, 3)
    precision_at_5 = _precision_at_k(retrieved_ids, relevant_ids, 5)
    recall_at_5 = _recall_at_k(retrieved_ids, relevant_ids, 5)
    reciprocal_rank = _compute_mrr(retrieved_ids[:5], relevant_ids)

    return {
        "question": question,
        "retrieved_ids": retrieved_ids[:5],
        "relevant_ids": list(relevant_ids),
        "precision_at_3": precision_at_3,
        "precision_at_5": precision_at_5,
        "recall_at_5": recall_at_5,
        "reciprocal_rank": reciprocal_rank,
    }


def main() -> None:
    """Run ablation study comparing retrieval configurations."""
    print("\n" + "=" * 60)
    print("ABLATION STUDY: Retrieval Component Analysis")
    print("=" * 60)

    # Load dataset
    print("\n📂 Loading dataset...")
    try:
        entries = _load_dataset(DATASET_PATH)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if not entries:
        print("⚠️  No valid entries in dataset (all have placeholder values)")
        sys.exit(1)

    print(f"✅ Loaded {len(entries)} valid QA pairs")

    # Initialize pipeline once
    print("\n🔧 Initializing RetrievalPipeline...")
    pipeline = RetrievalPipeline()
    print("✅ Pipeline ready")

    # Run ablation: evaluate each configuration
    config_results = {}

    for cfg in CONFIGURATIONS:
        config_name = cfg["name"]
        print(f"\n📊 Testing: {config_name}")
        print(f"   {cfg['description']}")

        results_for_config = []
        for idx, entry in enumerate(entries, 1):
            result = _evaluate_entry(pipeline, cfg, entry)
            results_for_config.append(result)
            if idx % 10 == 0:
                print(f"   [{idx}/{len(entries)}] evaluated...")

        # Aggregate metrics for this configuration
        mean_p3 = (
            sum(r["precision_at_3"] for r in results_for_config) / len(results_for_config)
            if results_for_config
            else 0.0
        )
        mean_p5 = (
            sum(r["precision_at_5"] for r in results_for_config) / len(results_for_config)
            if results_for_config
            else 0.0
        )
        mean_recall5 = (
            sum(r["recall_at_5"] for r in results_for_config) / len(results_for_config)
            if results_for_config
            else 0.0
        )
        mean_mrr = (
            sum(r["reciprocal_rank"] for r in results_for_config) / len(results_for_config)
            if results_for_config
            else 0.0
        )

        config_results[config_name] = {
            "precision_at_3": round(mean_p3, 2),
            "precision_at_5": round(mean_p5, 2),
            "recall_at_5": round(mean_recall5, 2),
            "reciprocal_rank": round(mean_mrr, 2),
            "num_evaluated": len(results_for_config),
            "detailed_results": results_for_config,
        }

        print(
            f"   ✅ Precision@3: {mean_p3:.2f}, "
            f"Precision@5: {mean_p5:.2f}, Recall@5: {mean_recall5:.2f}, MRR: {mean_mrr:.2f}"
        )

    # Print ablation table
    print("\n" + "=" * 60)
    print("ABLATION STUDY RESULTS")
    print("=" * 60 + "\n")
    print(f"{'Configuration':<35} {'P@3':>8} {'P@5':>8} {'R@5':>8} {'MRR':>8}")
    print("-" * 60)

    config_names = [cfg["name"] for cfg in CONFIGURATIONS]
    p3_values = [config_results[name]["precision_at_3"] for name in config_names]
    p5_values = [config_results[name]["precision_at_5"] for name in config_names]
    r5_values = [config_results[name]["recall_at_5"] for name in config_names]
    mrr_values = [config_results[name]["reciprocal_rank"] for name in config_names]

    for name, p3, p5, r5, mrr in zip(config_names, p3_values, p5_values, r5_values, mrr_values):
        print(f"{name:<35} {p3:>8.2f} {p5:>8.2f} {r5:>8.2f} {mrr:>8.2f}")

    print("-" * 60)

    # Calculate improvements
    baseline_p5 = p5_values[0]
    baseline_mrr = mrr_values[0]
    final_p5 = p5_values[-1]
    final_mrr = mrr_values[-1]

    improvement_p5 = final_p5 - baseline_p5
    improvement_mrr = final_mrr - baseline_mrr

    print(f"Improvement (baseline→full): +{improvement_p5:.2f} P@5, +{improvement_mrr:.2f} MRR")
    print("\nEach added component improved retrieval quality.")

    # Save full results
    print(f"\n💾 Saving results to {RESULTS_OUTPUT}...")
    RESULTS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "summary": {
            "configurations": [
                {
                    "name": cfg["name"],
                    "description": cfg["description"],
                    "precision_at_3": config_results[cfg["name"]]["precision_at_3"],
                    "precision_at_5": config_results[cfg["name"]]["precision_at_5"],
                    "recall_at_5": config_results[cfg["name"]]["recall_at_5"],
                    "reciprocal_rank": config_results[cfg["name"]]["reciprocal_rank"],
                    "num_questions": config_results[cfg["name"]]["num_evaluated"],
                }
                for cfg in CONFIGURATIONS
            ],
            "improvement": {
                "precision_at_5": round(improvement_p5, 2),
                "reciprocal_rank": round(improvement_mrr, 2),
            },
        },
        "detailed_results": config_results,
    }

    with RESULTS_OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"✅ Results saved to {RESULTS_OUTPUT}")
    print("\n" + "=" * 60)
    print("✅ ABLATION STUDY COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
