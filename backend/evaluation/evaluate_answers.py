"""Evaluate answer generation with a custom LLM-as-judge scoring pass."""

from __future__ import annotations

import json
import os
import sys
import time
import re
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

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

if load_dotenv is not None:
    project_dotenv = PROJECT_ROOT.parent / ".env"
    if project_dotenv.exists():
        load_dotenv(dotenv_path=project_dotenv, override=False)
    else:
        load_dotenv(override=False)

GROQ_API_KEYS = [
    os.environ.get("GROQ_API_KEY"),
    os.environ.get("GROQ_API_KEY_2"),
    os.environ.get("GROQ_API_KEY_3"),
]
GROQ_API_KEYS = [k for k in GROQ_API_KEYS if k]  # remove None values
current_key_index = 0


def get_llm(key_index: int, model: str | None = None) -> ChatGroq:
    selected_model = model or JUDGE_MODEL
    if GROQ_API_KEYS:
        return ChatGroq(
            model=selected_model,
            api_key=GROQ_API_KEYS[key_index % len(GROQ_API_KEYS)],
            temperature=0.3,
        )
    return ChatGroq(model=selected_model, temperature=0.3)


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True when exception is a Groq rate-limit style error."""
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        "ratelimiterror" in text
        or "rate limit" in text
        or "rate_limit_exceeded" in text
        or "error code: 429" in text
    )


def _rotate_key() -> tuple[int, int]:
    """Rotate to next configured key and return (old_index, new_index)."""
    global current_key_index
    old_index = current_key_index
    if GROQ_API_KEYS:
        current_key_index = (current_key_index + 1) % len(GROQ_API_KEYS)
    return old_index, current_key_index


def _invoke_with_key_failover(
    prompt: str,
    model: str,
    temperature: float,
    max_cycles: int = 2,
) -> str:
    """
    Invoke Groq with immediate key fallback when a rate-limit error occurs.

    Tries each configured key before retrying cycles. If no secondary keys are
    configured, this behaves like a normal single-key invoke.
    """
    if not prompt.strip():
        return ""

    keys_available = max(1, len(GROQ_API_KEYS))
    max_attempts = max_cycles * keys_available
    last_exc: Exception | None = None

    for _ in range(max_attempts):
        try:
            llm = get_llm(current_key_index, model=model)
            response = llm.invoke([HumanMessage(content=prompt)])
            return str(response.content).strip()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_rate_limit_error(exc) and len(GROQ_API_KEYS) > 1:
                old_idx, new_idx = _rotate_key()
                print(
                    f"⚠️  Rate limit on key {old_idx + 1}; switching to key {new_idx + 1}..."
                )
                continue
            raise

    raise RuntimeError(f"Groq key failover exhausted after {max_attempts} attempts: {last_exc}")


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


def _safe_mean(values: list[float]) -> float:
    """Return average or 0.0 for empty lists."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _build_judge_prompt(question: str, context: str, answer: str) -> str:
    return f"""You are evaluating a question answering system.

Question: {question}

Retrieved context:
{context}

Generated answer:
{answer}

Rate the answer on two dimensions. Return only a JSON object, nothing else:
{{
  "faithfulness": <float 0.0-1.0, how well the answer is supported by the context>,
  "answer_relevancy": <float 0.0-1.0, how well the answer addresses the question>
}}"""


def _extract_json_object(text: str) -> str:
    """Extract first JSON object from plain or fenced model output."""
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced_match:
        return fenced_match.group(1)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]

    return stripped


def _coerce_score(value: Any) -> float | None:
    try:
        score = float(value)
    except Exception:  # noqa: BLE001
        return None

    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def _parse_judge_scores(raw_response: str) -> tuple[float | None, float | None]:
    """Parse judge JSON response into (faithfulness, answer_relevancy)."""
    try:
        payload = json.loads(_extract_json_object(raw_response))
    except Exception:  # noqa: BLE001
        return None, None

    if not isinstance(payload, dict):
        return None, None

    faith = _coerce_score(payload.get("faithfulness"))
    relevancy = _coerce_score(payload.get("answer_relevancy"))
    return faith, relevancy


def _score_to_display(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def _safe_pass(value: float | None, threshold: float) -> bool:
    return (value is not None) and (value > threshold)


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
        prompt = qa_prompt(query=question, context=context, metadata=metadata)
        answer = _invoke_with_key_failover(
            prompt=prompt,
            model=JUDGE_MODEL,
            temperature=0.3,
        )
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
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-generation', action='store_true',
        help='Skip answer generation and load from saved file for judge scoring only')
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("ANSWER GENERATION & RAGAS EVALUATION")
    print("=" * 60)
    print(f"🔑 Groq keys detected for failover: {max(1, len(GROQ_API_KEYS))}")
    
    if args.skip_generation:
        # Load from saved file
        print("\n📂 Loading saved answers from generated_answers.json...")
        try:
            with ANSWERS_OUTPUT.open("r", encoding="utf-8") as f:
                generated_answers_data = json.load(f)
        except FileNotFoundError:
            print(f"❌ Saved answers not found at {ANSWERS_OUTPUT}")
            print("Run without --skip-generation to generate answers first.")
            sys.exit(1)
        
        print(f"✅ Loaded {len(generated_answers_data)} saved answers")
        

    else:
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
        
        # Generate answers
        print("\n💭 Generating answers...")
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

    # Run custom LLM-as-judge evaluation
    print("\n🔬 Running RAGAS evaluation (this may take a minute)...")
    try:
        faithfulness_values: list[float | None] = []
        answer_relevancy_values: list[float | None] = []
        context_precision_values: list[None] = []

        for i, entry in enumerate(generated_answers_data):
            question = str(entry.get("question", ""))
            answer = str(entry.get("generated_answer", ""))
            contexts = entry.get("contexts", [])
            if isinstance(contexts, list):
                context_text = "\n\n".join(str(c) for c in contexts)
            else:
                context_text = str(contexts)

            judge_prompt = _build_judge_prompt(
                question=question,
                context=context_text,
                answer=answer,
            )

            try:
                llm = get_llm(current_key_index, model=JUDGE_MODEL)
                response = llm.invoke([HumanMessage(content=judge_prompt)])
                faithfulness, answer_relevancy = _parse_judge_scores(str(response.content))
                if faithfulness is None or answer_relevancy is None:
                    print(
                        f"⚠️  Judge JSON parse issue on sample {i + 1}; storing null scores."
                    )
            except Exception as e:
                print(f"⚠️  Judge call failed on sample {i + 1}: {e}")
                if _is_rate_limit_error(e) and len(GROQ_API_KEYS) > 1:
                    old_idx, new_idx = _rotate_key()
                    print(
                        f"⚠️  Rate limit on key {old_idx + 1}; switching to key {new_idx + 1} for next call..."
                    )
                faithfulness, answer_relevancy = None, None

            faithfulness_values.append(faithfulness)
            answer_relevancy_values.append(answer_relevancy)
            context_precision_values.append(None)

            if i < len(generated_answers_data) - 1:
                time.sleep(2)

        faithfulness_score = _safe_mean([v for v in faithfulness_values if v is not None])
        answer_relevancy_score = _safe_mean([v for v in answer_relevancy_values if v is not None])
        context_precision_score: float | None = None
        
        # Print results
        print("\n" + "=" * 60)
        print("ANSWER QUALITY RESULTS (RAGAS)")
        print("=" * 60)
        print(f"Faithfulness      : {_score_to_display(faithfulness_score)}   (grounded in retrieved chunks)")
        print(f"Answer Relevancy  : {_score_to_display(answer_relevancy_score)}   (answers address the question)")
        print(f"Context Precision : {_score_to_display(context_precision_score)}   (relevant chunks ranked higher)")
        
        print("\n" + "-" * 60)
        print("INTERPRETATION")
        print("-" * 60)
        
        faith_pass = "✅ PASS" if _safe_pass(faithfulness_score, 0.7) else "❌ FAIL"
        relevancy_pass = "✅ PASS" if _safe_pass(answer_relevancy_score, 0.65) else "❌ FAIL"
        
        print(f"Faithfulness > 0.7      = answers well grounded     {faith_pass}")
        print(f"Answer Relevancy > 0.65 = answers address questions {relevancy_pass}")
        
        # Save full results
        results_data = {
            "metrics": {
                "faithfulness": float(faithfulness_score),
                "answer_relevancy": float(answer_relevancy_score),
                "context_precision": None,
            },
            "pass_fail": {
                "faithfulness": _safe_pass(faithfulness_score, 0.7),
                "answer_relevancy": _safe_pass(answer_relevancy_score, 0.65),
            },
            "per_sample_results": [],
        }
        
        # Add per-sample detailed results
        for i, entry in enumerate(generated_answers_data):
            sample_result = {
                "question": entry["question"],
                "section_id": entry["section_id"],
                "section_title": entry["section_title"],
                "faithfulness": faithfulness_values[i] if i < len(faithfulness_values) else None,
                "answer_relevancy": answer_relevancy_values[i] if i < len(answer_relevancy_values) else None,
                "context_precision": None,
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
        print(f"❌ Evaluation failed: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
