"""Evaluate answer generation using RAGAS metrics (Faithfulness, Answer Relevancy, Context Precision)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Install check for RAGAS
try:
    import datasets
    from ragas import evaluate
    from ragas.metrics import faithfulness, answer_relevancy, context_precision
    from ragas.llms import LangchainLLMWrapper
except ImportError as e:
    print("❌ RAGAS dependencies are required for this evaluation.")
    print("\nInstall with:")
    print("  pip install ragas datasets langchain-groq")
    print("\nOr run:")
    print("  pip install -r evaluation/requirements_eval.txt")
    sys.exit(1)

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rag.retrieval import RetrievalPipeline  # type: ignore[import-not-found]
from rag.prompts import qa_prompt  # type: ignore[import-not-found]
from evaluation.config import RESULTS_DIR, JUDGE_MODEL, PAPERS  # type: ignore[import-not-found]


DATASET_PATH = PROJECT_ROOT / "evaluation/dataset/qa_pairs.json"
RESULTS_OUTPUT = PROJECT_ROOT / RESULTS_DIR / "answer_results.json"
ANSWERS_OUTPUT = PROJECT_ROOT / RESULTS_DIR / "generated_answers.json"


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
        # Skip if contains placeholder text
        if "FILL IN" in entry.get("question", ""):
            continue
        reference_answer = entry.get("reference_answer", "")
        if "FILL IN" in reference_answer:
            continue
        relevant_ids = entry.get("relevant_chunk_ids") or []
        if any("FILL IN" in str(rid) for rid in relevant_ids):
            continue
        filtered.append(entry)

    return filtered


def _result_content(result: Any) -> str:
    """Extract content string from RetrievalResult or dict."""
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    return str(content or "")


def _result_metadata(result: Any) -> dict:
    """Extract metadata dictionary from RetrievalResult or dict."""
    metadata = getattr(result, "metadata", None)
    if metadata is None and isinstance(result, dict):
        metadata = result.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _result_score(result: Any) -> float:
    """Extract numeric score from RetrievalResult or dict."""
    score = getattr(result, "score", None)
    if score is None and isinstance(result, dict):
        score = result.get("score")
    try:
        return float(score)
    except Exception:  # noqa: BLE001
        return 0.0


def _is_reference_result(result: Any) -> bool:
    """Return True when chunk metadata indicates a references/bibliography section."""
    metadata = _result_metadata(result)
    section_title = metadata.get("section_title", "")
    
    # Reference section patterns
    if isinstance(section_title, str):
        heading = " ".join(section_title.split()).lower()
        if any(keyword in heading for keyword in ["reference", "bibliography", "citations"]):
            return True
    
    return False


def _build_qa_context(chunks: list[Any]) -> str:
    """Format chunk snippets into QA prompt context (replicate graph.py format)."""
    context_parts = []
    context_idx = 1
    
    for chunk in chunks:
        if _is_reference_result(chunk):
            continue

        metadata = _result_metadata(chunk)
        section_title = metadata.get("section_title")
        chunk_text = _result_content(chunk)

        if isinstance(section_title, str) and section_title.strip():
            context_parts.append(
                f"[{context_idx}] (Section: {section_title.strip()})\n{chunk_text}"
            )
        else:
            context_parts.append(f"[{context_idx}]\n{chunk_text}")
        context_idx += 1

    return "\n\n".join(context_parts)


def _generate_answer(
    pipeline: RetrievalPipeline,
    question: str,
    section_id: str,
    document_id: str,
    paper_title: str,
    paper_type: str,
    top_k: int = 5,
) -> tuple[str, list[str]]:
    """
    Generate answer using RetrievalPipeline and Groq LLM.
    
    Returns:
        (generated_answer, list_of_context_chunks)
    """
    # 1. Retrieve chunks
    results = pipeline.retrieve_with_section_scope(
        query=question,
        section_id=section_id,
        document_id=document_id,
        top_k=top_k,
        rerank=True,
    )
    
    # 2. Extract non-reference chunks
    hits = [chunk for chunk in results if not _is_reference_result(chunk)]
    
    if not hits:
        return "No relevant content found.", []
    
    # 3. Build context using same format as graph.py
    context = _build_qa_context(hits)
    
    if not context.strip():
        return "No relevant content available.", []
    
    # 4. Build metadata for prompt
    metadata = {
        "paper_title": paper_title,
        "category": paper_type,
    }
    
    # 5. Call Groq LLM with qa_prompt format from graph.py
    try:
        llm = ChatGroq(model=JUDGE_MODEL, temperature=0.3)
        prompt = qa_prompt(query=question, context=context, metadata=metadata)
        response = llm.invoke([HumanMessage(content=prompt)])
        answer = response.content.strip()
    except Exception as exc:
        print(f"❌ LLM error: {exc}")
        answer = "Error generating answer."
    
    # 6. Extract context strings for RAGAS
    context_chunks = []
    for result in hits:
        chunk_content = _result_content(result)
        if chunk_content.strip():
            context_chunks.append(chunk_content)
    
    return answer, context_chunks


def main() -> None:
    """Main evaluation function."""
    print("\n" + "=" * 60)
    print("ANSWER GENERATION & RAGAS EVALUATION")
    print("=" * 60)
    
    # Load dataset
    print("\n📂 Loading dataset...")
    try:
        dataset_entries = _load_dataset(DATASET_PATH)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    if not dataset_entries:
        print("⚠️  No valid entries in dataset (all entries have placeholder values)")
        sys.exit(1)
    
    print(f"✅ Loaded {len(dataset_entries)} entries")
    
    # Initialize pipeline
    print("\n🔧 Initializing RetrievalPipeline...")
    pipeline = RetrievalPipeline()
    print("✅ Pipeline ready")
    
    # Generate answers and collect RAGAS inputs
    print("\n💭 Generating answers...")
    ragas_data = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }
    generated_answers_data = []
    
    for idx, entry in enumerate(dataset_entries, 1):
        question = entry.get("question", "")
        section_id = entry.get("section_id", "")
        document_id = entry.get("document_id", "")
        reference_answer = entry.get("reference_answer", "")
        paper_id = entry.get("paper_id", "")
        paper_type = entry.get("paper_type", "Applied")
        section_title = entry.get("section_title", "")
        
        # Find paper title from PAPERS config
        paper_title = next(
            (p["title"] for p in PAPERS if p["paper_id"] == paper_id),
            "Unknown Paper"
        )
        
        print(f"  [{idx}/{len(dataset_entries)}] Generating answer: {question[:70]}...")
        
        # Generate answer
        answer, context_chunks = _generate_answer(
            pipeline,
            question=question,
            section_id=section_id,
            document_id=document_id,
            paper_title=paper_title,
            paper_type=paper_type,
        )
        
        # Add to RAGAS dataset
        ragas_data["question"].append(question)
        ragas_data["answer"].append(answer)
        ragas_data["contexts"].append(context_chunks)
        ragas_data["ground_truth"].append(reference_answer)
        
        # Store for detailed results
        generated_answers_data.append({
            "question": question,
            "section_id": section_id,
            "section_title": section_title,
            "generated_answer": answer,
            "reference_answer": reference_answer,
            "contexts": context_chunks,
        })
    
    # Save generated answers
    print(f"\n💾 Saving generated answers to {ANSWERS_OUTPUT}...")
    ANSWERS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ANSWERS_OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(generated_answers_data, f, indent=2)
    print(f"✅ Saved to {ANSWERS_OUTPUT}")
    
    # Configure RAGAS
    print("\n⚙️  Configuring RAGAS...")
    llm = ChatGroq(model=JUDGE_MODEL, temperature=0.3)
    llm_wrapper = LangchainLLMWrapper(llm)
    print("✅ RAGAS configured with Groq LLM")
    
    # Build HuggingFace Dataset
    print("\n📊 Building HuggingFace Dataset...")
    hf_dataset = datasets.Dataset.from_dict(ragas_data)
    print(f"✅ Dataset created with {len(hf_dataset)} samples")
    
    # Run RAGAS evaluation
    print("\n🔬 Running RAGAS evaluation (this may take a minute)...")
    try:
        results = evaluate(
            dataset=hf_dataset,
            metrics=[faithfulness, answer_relevancy, context_precision],
            llm=llm_wrapper,
        )
        
        # Extract scores
        faithfulness_score = results["faithfulness"].score
        answer_relevancy_score = results["answer_relevancy"].score
        context_precision_score = results["context_precision"].score
        
        # Print results
        print("\n" + "=" * 60)
        print("ANSWER QUALITY RESULTS (RAGAS)")
        print("=" * 60)
        print(f"Faithfulness      : {faithfulness_score:.2f}   (grounded in retrieved chunks)")
        print(f"Answer Relevancy  : {answer_relevancy_score:.2f}   (answers address the question)")
        print(f"Context Precision : {context_precision_score:.2f}   (relevant chunks ranked higher)")
        
        print("\n" + "-" * 60)
        print("INTERPRETATION")
        print("-" * 60)
        
        faith_pass = "✅ PASS" if faithfulness_score > 0.7 else "❌ FAIL"
        relevancy_pass = "✅ PASS" if answer_relevancy_score > 0.65 else "❌ FAIL"
        
        print(f"Faithfulness > 0.7      = answers well grounded     {faith_pass}")
        print(f"Answer Relevancy > 0.65 = answers address questions {relevancy_pass}")
        
        # Save full results
        results_data = {
            "metrics": {
                "faithfulness": float(faithfulness_score),
                "answer_relevancy": float(answer_relevancy_score),
                "context_precision": float(context_precision_score),
            },
            "pass_fail": {
                "faithfulness": faithfulness_score > 0.7,
                "answer_relevancy": answer_relevancy_score > 0.65,
            },
            "per_sample_results": [],
        }
        
        # Add per-sample detailed results
        for i, entry in enumerate(generated_answers_data):
            sample_result = {
                "question": entry["question"],
                "section_id": entry["section_id"],
                "section_title": entry["section_title"],
                "faithfulness": float(results["faithfulness"].scores[i]) if hasattr(results["faithfulness"], "scores") else None,
                "answer_relevancy": float(results["answer_relevancy"].scores[i]) if hasattr(results["answer_relevancy"], "scores") else None,
                "context_precision": float(results["context_precision"].scores[i]) if hasattr(results["context_precision"], "scores") else None,
            }
            results_data["per_sample_results"].append(sample_result)
        
        print(f"\n💾 Saving detailed results to {RESULTS_OUTPUT}...")
        RESULTS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with RESULTS_OUTPUT.open("w", encoding="utf-8") as f:
            json.dump(results_data, f, indent=2)
        print(f"✅ Saved to {RESULTS_OUTPUT}")
        
        print("\n" + "=" * 60)
        print("✅ EVALUATION COMPLETE")
        print("=" * 60)
        print(f"\nResults saved:")
        print(f"  • {RESULTS_OUTPUT}")
        print(f"  • {ANSWERS_OUTPUT}")
        
    except Exception as exc:
        print(f"❌ RAGAS evaluation failed: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
