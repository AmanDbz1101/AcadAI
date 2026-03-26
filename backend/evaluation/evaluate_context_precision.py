"""Evaluate context precision separately using LLM-as-judge for chunk relevance ranking."""

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

from evaluation.config import RESULTS_DIR, JUDGE_MODEL  # type: ignore[import-not-found]

ANSWERS_OUTPUT = PROJECT_ROOT / RESULTS_DIR / "generated_answers.json"
RESULTS_OUTPUT = PROJECT_ROOT / RESULTS_DIR / "answer_results.json"

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


def _build_chunk_relevance_prompt(question: str, chunks: list[str]) -> str:
    """Build prompt to judge relevance of each chunk to the question."""
    chunk_text = ""
    for i, chunk in enumerate(chunks, 1):
        chunk_text += f"\n[Chunk {i}]\n{chunk}\n"
    
    return f"""You are evaluating the relevance of retrieved context chunks to a question.

Question: {question}

Retrieved chunks:
{chunk_text}

For each chunk, determine if it is relevant to answering the question (provides information directly useful for answering).
Return only a JSON object mapping chunk indices to boolean relevance:
{{
  "1": true,
  "2": false,
  "3": true,
  ...
}}

Use true/false for relevance. Include all chunks by index."""


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


def _parse_chunk_relevances(raw_response: str, num_chunks: int) -> dict[int, bool | None]:
    """Parse judge JSON response into chunk index -> relevance boolean mapping."""
    try:
        payload = json.loads(_extract_json_object(raw_response))
    except Exception:  # noqa: BLE001
        return {}

    if not isinstance(payload, dict):
        return {}

    result = {}
    for i in range(1, num_chunks + 1):
        key = str(i)
        if key in payload:
            try:
                result[i] = bool(payload[key])
            except Exception:  # noqa: BLE001
                pass

    return result


def _compute_context_precision(
    chunk_relevances: dict[int, bool | None],
    num_chunks: int,
) -> float | None:
    """
    Compute context precision: ratio of relevant chunks in retrieved set to total relevant chunks.
    
    If no chunks are marked as relevant, precision is 0.0.
    If no relevance data available, return None.
    """
    if not chunk_relevances:
        return None

    # Count how many chunks the judge found relevant
    relevant_count = sum(1 for v in chunk_relevances.values() if v is True)
    
    # If no relevant chunks, precision is 0
    if relevant_count == 0:
        return 0.0
    
    # Precision = (number of relevant chunks) / (total chunks retrieved)
    # This is a simplified version; RAGAS context_precision checks if relevant chunks
    # appear early in the ranking, but we'll use proportion of relevant chunks.
    precision = relevant_count / num_chunks
    return precision


def main() -> None:
    """Evaluate context precision and update answer_results.json."""
    print("\n" + "=" * 60)
    print("CONTEXT PRECISION EVALUATION")
    print("=" * 60)
    print(f"🔑 Groq keys detected for failover: {max(1, len(GROQ_API_KEYS))}")
    
    # Load generated answers
    print("\n📂 Loading generated answers...")
    try:
        with ANSWERS_OUTPUT.open("r", encoding="utf-8") as f:
            generated_answers_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Generated answers not found at {ANSWERS_OUTPUT}")
        print("Run evaluate_answers.py first to generate answers.")
        sys.exit(1)
    
    print(f"✅ Loaded {len(generated_answers_data)} answers")
    
    # Load results to update
    print("\n📂 Loading existing results...")
    try:
        with RESULTS_OUTPUT.open("r", encoding="utf-8") as f:
            results_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Results not found at {RESULTS_OUTPUT}")
        print("Run evaluate_answers.py first to generate results.")
        sys.exit(1)
    
    print(f"✅ Loaded existing results")
    
    # Score context precision for each question
    print("\n🔬 Evaluating context precision...")
    context_precision_values: list[float | None] = []
    
    for i, entry in enumerate(generated_answers_data):
        question = str(entry.get("question", ""))
        contexts = entry.get("contexts", [])
        
        if not isinstance(contexts, list):
            contexts = [contexts]
        
        num_chunks = len(contexts)
        
        if num_chunks == 0:
            print(f"  [{i + 1}/{len(generated_answers_data)}] No chunks; precision = 0.0")
            context_precision_values.append(0.0)
            continue
        
        # Build and invoke judge prompt
        judge_prompt = _build_chunk_relevance_prompt(
            question=question,
            chunks=contexts,
        )
        
        try:
            llm = get_llm(current_key_index, model=JUDGE_MODEL)
            response = llm.invoke([HumanMessage(content=judge_prompt)])
            chunk_relevances = _parse_chunk_relevances(str(response.content), num_chunks)
            
            if not chunk_relevances:
                print(
                    f"  [{i + 1}/{len(generated_answers_data)}] Judge JSON parse issue; setting precision = None"
                )
                context_precision_values.append(None)
            else:
                precision = _compute_context_precision(chunk_relevances, num_chunks)
                context_precision_values.append(precision)
                precision_display = f"{precision:.2f}" if precision is not None else "N/A"
                print(
                    f"  [{i + 1}/{len(generated_answers_data)}] {num_chunks} chunks; precision = {precision_display}"
                )
        
        except Exception as e:
            print(f"⚠️  Judge call failed on sample {i + 1}: {e}")
            if _is_rate_limit_error(e) and len(GROQ_API_KEYS) > 1:
                old_idx, new_idx = _rotate_key()
                print(
                    f"⚠️  Rate limit on key {old_idx + 1}; switching to key {new_idx + 1} for next call..."
                )
            context_precision_values.append(None)
        
        if i < len(generated_answers_data) - 1:
            time.sleep(2)
    
    # Compute aggregate metric (average of non-null values)
    valid_precision_values = [v for v in context_precision_values if v is not None]
    if valid_precision_values:
        aggregate_precision = sum(valid_precision_values) / len(valid_precision_values)
    else:
        aggregate_precision = None
    
    # Update answer_results.json with context_precision values
    print("\n💾 Updating results with context precision scores...")
    results_data["metrics"]["context_precision"] = aggregate_precision
    
    for i, entry in enumerate(results_data["per_sample_results"]):
        if i < len(context_precision_values):
            entry["context_precision"] = context_precision_values[i]
    
    # Save updated results
    with RESULTS_OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2)
    print(f"✅ Saved updated results to {RESULTS_OUTPUT}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("CONTEXT PRECISION RESULTS")
    print("=" * 60)
    display_value = f"{aggregate_precision:.2f}" if aggregate_precision is not None else "N/A"
    print(f"Aggregate Context Precision : {display_value}   (relevant chunks in retrieval)")
    print("\n" + "=" * 60)
    print("✅ CONTEXT PRECISION EVALUATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
