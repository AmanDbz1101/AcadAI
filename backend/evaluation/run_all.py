"""Run all evaluations in sequence and produce a final summary report."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main() -> None:
    """Run all evaluations and produce consolidated summary."""
    print("\n" + "=" * 60)
    print("AcadAI - COMPREHENSIVE EVALUATION SUITE")
    print("=" * 60)
    print("\nRunning all evaluations in sequence...\n")

    # Define evaluation modules
    evaluations = [
        {
            "name": "Retrieval Evaluation",
            "module": "evaluation.evaluate_retrieval",
            "results_file": PROJECT_ROOT / "evaluation/results/retrieval_results.json",
        },
        {
            "name": "Answer Generation & RAGAS Evaluation",
            "module": "evaluation.evaluate_answers",
            "results_file": PROJECT_ROOT / "evaluation/results/answer_results.json",
        },
        {
            "name": "Ablation Study",
            "module": "evaluation.evaluate_ablation",
            "results_file": PROJECT_ROOT / "evaluation/results/ablation_results.json",
        },
    ]

    results = {}
    failed_evaluations = []

    # Run each evaluation
    for eval_config in evaluations:
        eval_name = eval_config["name"]
        module_name = eval_config["module"]

        print(f"\n{'=' * 60}")
        print(f"▶️  Starting: {eval_name}")
        print(f"{'=' * 60}")

        try:
            # Dynamically import the module and call main()
            module = __import__(module_name, fromlist=["main"])
            if hasattr(module, "main"):
                module.main()
                results[eval_name] = "✅ PASSED"
                print(f"\n✅ {eval_name} completed successfully")
            else:
                results[eval_name] = "❌ FAILED (no main() function)"
                failed_evaluations.append(eval_name)
                print(f"❌ {eval_name} failed: main() function not found")

        except Exception as exc:
            results[eval_name] = f"❌ FAILED ({str(exc)[:50]}...)"
            failed_evaluations.append(eval_name)
            print(f"\n❌ {eval_name} failed with error:")
            print(f"   {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()

    # Load results from JSON files
    print(f"\n{'=' * 60}")
    print("LOADING RESULTS")
    print(f"{'=' * 60}")

    retrieval_metrics = _load_retrieval_results(
        PROJECT_ROOT / "evaluation/results/retrieval_results.json"
    )
    answer_metrics = _load_answer_results(
        PROJECT_ROOT / "evaluation/results/answer_results.json"
    )
    ablation_metrics = _load_ablation_results(
        PROJECT_ROOT / "evaluation/results/ablation_results.json"
    )

    # Print consolidated summary
    print(f"\n{'=' * 60}")
    print("AcadAI EVALUATION SUMMARY")
    print(f"{'=' * 60}\n")

    if retrieval_metrics:
        print("RETRIEVAL QUALITY")
        print(f"  Precision@5 : {retrieval_metrics['p5']:.3f}")
        print(f"  Recall@5    : {retrieval_metrics['recall']:.3f}")
        print(f"  MRR         : {retrieval_metrics['mrr']:.3f}\n")
    else:
        print("RETRIEVAL QUALITY")
        print("  ❌ Results not available\n")

    if answer_metrics:
        print("ANSWER QUALITY (RAGAS)")
        faithfulness = answer_metrics.get("faithfulness", "N/A")
        relevancy = answer_metrics.get("answer_relevancy", "N/A")
        precision = answer_metrics.get("context_precision", "N/A")
        print(f"  Faithfulness      : {faithfulness}")
        print(f"  Answer Relevancy  : {relevancy}")
        print(f"  Context Precision : {precision}\n")
    else:
        print("ANSWER QUALITY (RAGAS)")
        print("  ❌ Results not available\n")

    if ablation_metrics:
        print("ABLATION (Full System vs Dense Only)")
        p5_improvement = ablation_metrics.get("p5_improvement", "N/A")
        mrr_improvement = ablation_metrics.get("mrr_improvement", "N/A")
        print(f"  P@5 improvement : +{p5_improvement}")
        print(f"  MRR improvement : +{mrr_improvement}\n")
    else:
        print("ABLATION (Full System vs Dense Only)")
        print("  ❌ Results not available\n")

    # Print status summary
    print("=" * 60)
    print("EVALUATION STATUS")
    print("=" * 60)
    for eval_name, status in results.items():
        print(f"  {eval_name:<40} {status}")

    if failed_evaluations:
        print(f"\n⚠️  {len(failed_evaluations)} evaluation(s) failed:")
        for name in failed_evaluations:
            print(f"    • {name}")
    else:
        print("\n✅ All evaluations completed successfully!")

    print(f"\n📁 All results saved to: {PROJECT_ROOT / 'evaluation/results/'}")
    print("=" * 60)


def _load_retrieval_results(path: Path) -> Optional[dict[str, Any]]:
    """Load and extract retrieval metrics from JSON file."""
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # Data is a direct list of results
        if not isinstance(data, list):
            return None

        # Extract aggregated metrics
        p5_values = [r["precision_at_5"] for r in data if "precision_at_5" in r]
        recall_values = [r["recall_at_5"] for r in data if "recall_at_5" in r]
        mrr_values = [r["reciprocal_rank"] for r in data if "reciprocal_rank" in r]

        if not p5_values:
            return None

        return {
            "p5": sum(p5_values) / len(p5_values),
            "recall": sum(recall_values) / len(recall_values),
            "mrr": sum(mrr_values) / len(mrr_values),
        }
    except Exception:
        return None


def _load_answer_results(path: Path) -> Optional[dict[str, Any]]:
    """Load and extract answer generation metrics from JSON file."""
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        metrics = data.get("metrics", {})
        return {
            "faithfulness": f"{metrics.get('faithfulness', 0):.2f}",
            "answer_relevancy": f"{metrics.get('answer_relevancy', 0):.2f}",
            "context_precision": f"{metrics.get('context_precision', 0):.2f}",
        }
    except Exception:
        return None


def _load_ablation_results(path: Path) -> Optional[dict[str, Any]]:
    """Load and extract ablation study improvements from JSON file."""
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        improvement = data.get("summary", {}).get("improvement", {})
        return {
            "p5_improvement": f"{improvement.get('precision_at_5', 0):.2f}",
            "mrr_improvement": f"{improvement.get('reciprocal_rank', 0):.2f}",
        }
    except Exception:
        return None


if __name__ == "__main__":
    main()
