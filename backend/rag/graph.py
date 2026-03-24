"""
Research Paper Assistant - Graph
=================================
Unified LangGraph workflow for paper analysis.

Follows the Chat2Code pattern: simple, elegant node functions with lazy agent initialization.

Workflow paths:
    1. Extraction + Categorization:
       START → extraction → categorizer → END
    
    2. Q&A (with query):
       START → extraction → categorizer → retrieve_and_qa → END
    
    3. Summarization (no query, unknown category):
       START → extraction → categorizer → summarizer → END
    
    4. Reading Guide (no query):
       START → extraction → categorizer → <category_guide> → retrieve_and_qa → END
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import inspect
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from config import MIN_RELEVANCE_THRESHOLD
from rag.states import AgentState, RetrievalResult
from rag.prompts import (
    categorizer_prompt,
    qa_prompt,
    summarizer_prompt,
    applied_guide_prompt,
    theoretical_guide_prompt,
    survey_guide_prompt,
)
from rag.guide_models import (
    AppliedReadingGuide,
    TheoreticalReadingGuide,
    SurveyReadingGuide,
)
from rag.retrieval.config import (
    SCOPED_TOP_K,
    FALLBACK_TOP_K,
    RERANKER_TOP_N,
    QA_TOP_K,
    MAX_GUIDE_QUESTIONS,
    MAX_PARALLEL_QUESTIONS,
)

# ---------------------------------------------------------------------------
# Guide helper: extract questions_to_answer and sections_to_read from any guide
# ---------------------------------------------------------------------------

def _extract_guide_retrieval_info(guide_json: dict) -> list[dict]:
    """
    Walk all ReadingPass objects inside a guide dict and return a flat list of
    per-question entries, each carrying **only the sections from that step**.

    Return format::

        [
            {"question": "...", "sections": ["Abstract", "1 Introduction"]},
            {"question": "...", "sections": ["3 Model Architecture"]},
            ...
        ]

    Multiple questions that belong to the same step share the same sections list
    (the exact sections listed for that step only — not accumulating across steps).

    Works for all three guide shapes (applied, theoretical, survey).
    """
    pairs: list[dict] = []
    seen_questions: set[str] = set()

    # All known pass keys across the three guide models
    pass_keys = [
        "pass1_quick_scan",
        "pass2_method_understanding",
        "pass3_deep_analysis",
        "pass1_field_overview",
        "pass2_taxonomy_understanding",
        "pass3_research_landscape_analysis",
        "pass2_proof_strategy",
        "pass3_deep_mathematical_analysis",
    ]

    for key in pass_keys:
        reading_pass = guide_json.get(key)
        if not reading_pass:
            continue
        for step in reading_pass.get("steps", []):
            # Sections are scoped to this step only
            step_sections = [s for s in step.get("section_to_read", []) if s]
            needs_figures = bool(step.get("needs_figures", False))
            needs_tables = bool(step.get("needs_tables", False))
            for q in step.get("questions_to_answer", []):
                if q and q not in seen_questions:
                    seen_questions.add(q)
                    pairs.append(
                        {
                            "question": q,
                            "sections": step_sections,
                            "needs_figures": needs_figures,
                            "needs_tables": needs_tables,
                        }
                    )

    return pairs


def _retrieve_with_section_id_scope(
    pipeline,
    question: str,
    section_id: str,
    document_id: str,
) -> list:
    """
    Retrieve chunks scoped to a specific section ID and its descendants.

    This helper enables section-aware retrieval using the new section_path_ids
    feature, which allows parent sections to automatically include all descendant
    sections in the results.

    Parameters
    ----------
    pipeline : RetrievalPipeline
        The retrieval pipeline instance.
    question : str
        The search query.
    section_id : str
        The section ID to scope results to (e.g., "3.2"). The filter will
        match any chunk whose section_path_ids contains this ID.
    document_id : str
        The document ID being queried.

    Returns
    -------
    list[RetrievalResult]
        Chunks within the specified section scope, sorted by rerank score.

    Notes
    -----
    - This function uses the new `retrieve_with_section_scope()` method on the
      pipeline, which filters based on section_path_ids (ID ancestry) rather
      than section_path (title ancestry).
    - Parent sections automatically include all descendants.
    - Falls back to empty list if no results found.

    See Also
    --------
    RetrievalPipeline.retrieve_with_section_scope : Core section-scoped retrieval API.
    """
    if not section_id or not document_id:
        logger.warning(
            "_retrieve_with_section_id_scope: missing section_id or document_id;"
            " skipping scoped retrieval"
        )
        return []

    try:
        results = pipeline.retrieve_with_section_scope(
            query=question,
            section_id=section_id,
            document_id=document_id,
            top_k=SCOPED_TOP_K,
            top_n=SCOPED_TOP_K,
            rerank=False,
        )
        logger.debug(
            "Section-scoped retrieval for question '%s' (section_id=%s): "
            "retrieved %d chunks",
            question[:70],
            section_id,
            len(results),
        )
        return results
    except Exception as exc:
        logger.warning(
            "Section-scoped retrieval failed for section_id=%s: %s",
            section_id,
            exc,
        )
        return []


# Retrieval pipeline (lazy singleton — imported here to keep graph.py clean)
_retrieval_pipeline = None


def _get_retrieval_pipeline():
    """Return a process-wide RetrievalPipeline singleton."""
    global _retrieval_pipeline
    if _retrieval_pipeline is None:
        from rag.retrieval import RetrievalPipeline

        _retrieval_pipeline = RetrievalPipeline()
    return _retrieval_pipeline

# Import extraction orchestrator
import sys
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from backend.extraction.extraction import PDFExtractor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON extraction helper (from old categorizer_agent.py)
# ---------------------------------------------------------------------------
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from LLM response."""
    # Try markdown-fenced JSON first
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return json.loads(match.group(1))
    
    # Try parsing the whole response as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Last resort – find the first {...} span
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(text[start:end])
    
    raise ValueError(f"No valid JSON found in LLM response:\n{text}")


# Retrieval helper caches and heuristics
_section_lookup_cache: dict[str, dict[str, list[str]]] = {}

_FACTUAL_PREFIXES = (
    "what is",
    "define",
    "how many",
    "when",
    "who",
    "which",
)

_REFERENCE_SECTION_HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*)?\s*[:.)-]?\s*(?:references?|bibliography|works cited)\b",
    flags=re.IGNORECASE,
)


def _normalize_section_name(section_name: str) -> str:
    """Normalize section labels for exact/fuzzy matching."""
    normalized = section_name.strip().lower()
    normalized = re.sub(r"^\d+(?:\.\d+)*\s*[:.)-]?\s*", "", normalized)
    return " ".join(normalized.split())


def _strip_section_numbering(section_name: str) -> str:
    """Remove common numeric prefixes from section labels."""
    return re.sub(r"^\s*\d+(?:\.\d+)*\s*[:.)-]?\s*", "", section_name).strip()


def _flatten_section_headings(sections: list[dict[str, Any]] | None) -> list[str]:
    """Flatten nested section dictionaries into a unique ordered heading list."""
    if not sections:
        return []

    headings: list[str] = []
    seen: set[str] = set()

    def _walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            heading = str(node.get("original_name") or node.get("title") or "").strip()
            if heading and heading not in seen:
                seen.add(heading)
                headings.append(heading)

            children = node.get("sections") or []
            if isinstance(children, list) and children:
                _walk(children)

    _walk(sections)
    return headings


def _build_heading_pattern(heading: str) -> re.Pattern[str]:
    """Build a tolerant line-based regex for matching a section heading."""
    normalized = " ".join(heading.split())
    escaped = re.escape(normalized).replace(r"\ ", r"\s+")
    return re.compile(rf"(?im)^\s*{escaped}\s*$")


def _find_heading_bounds(full_text: str, heading: str, start_pos: int = 0) -> tuple[int, int] | None:
    """Find heading start/end character offsets in full text."""
    if not full_text or not heading:
        return None

    candidates = [heading]
    stripped = _strip_section_numbering(heading)
    if stripped and stripped.lower() != heading.lower():
        candidates.append(stripped)

    for candidate in candidates:
        match = _build_heading_pattern(candidate).search(full_text, start_pos)
        if match:
            return match.start(), match.end()

    if stripped:
        escaped = re.escape(" ".join(stripped.split())).replace(r"\ ", r"\s+")
        relaxed = re.compile(
            rf"(?im)^\s*(?:\d+(?:\.\d+)*)?\s*[:.)-]?\s*{escaped}\s*$"
        )
        match = relaxed.search(full_text, start_pos)
        if match:
            return match.start(), match.end()

    return None


def _extract_section_text_from_full_text(
    full_text: str,
    section_headings: list[str],
    keywords: tuple[str, ...],
    max_chars: int = 1800,
) -> str:
    """Extract a section snippet by matching heading keywords in full text."""
    if not full_text or not section_headings:
        return ""

    target_index = None
    for idx, heading in enumerate(section_headings):
        normalized = _normalize_section_name(heading)
        if any(keyword in normalized for keyword in keywords):
            target_index = idx
            break

    if target_index is None:
        return ""

    target_bounds = _find_heading_bounds(full_text, section_headings[target_index])
    if target_bounds is None:
        return ""

    start = target_bounds[1]
    end = len(full_text)
    for next_heading in section_headings[target_index + 1 :]:
        next_bounds = _find_heading_bounds(full_text, next_heading, start)
        if next_bounds is not None:
            end = next_bounds[0]
            break

    section_text = full_text[start:end].strip()
    section_text = re.sub(r"\n{3,}", "\n\n", section_text)
    if len(section_text) > max_chars:
        section_text = section_text[:max_chars].rsplit(" ", 1)[0].rstrip() + "..."
    return section_text


def _extract_intro_conclusion_context(
    full_text: str,
    sections: list[dict[str, Any]] | None,
) -> tuple[str, str]:
    """Return best-effort introduction and conclusion snippets for prompt grounding."""
    headings = _flatten_section_headings(sections)

    introduction = _extract_section_text_from_full_text(
        full_text=full_text,
        section_headings=headings,
        keywords=("introduction",),
    )
    conclusion = _extract_section_text_from_full_text(
        full_text=full_text,
        section_headings=headings,
        keywords=("conclusion", "conclusions", "summary", "future work"),
    )

    if not introduction:
        introduction = "Not available in extracted full text."
    if not conclusion:
        conclusion = "Not available in extracted full text."

    return introduction, conclusion


def _load_section_lookup(document_id: str) -> dict[str, list[str]]:
    """Load and cache the section lookup sidecar for a document."""
    if not document_id:
        return {}
    if document_id in _section_lookup_cache:
        return _section_lookup_cache[document_id]

    lookup_path = Path("output") / f"{document_id}_sections.json"
    if not lookup_path.exists():
        _section_lookup_cache[document_id] = {}
        return {}

    try:
        with open(lookup_path, encoding="utf-8") as f:
            lookup = json.load(f)
        if not isinstance(lookup, dict):
            lookup = {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load section lookup for %s: %s", document_id, exc)
        lookup = {}

    _section_lookup_cache[document_id] = lookup
    return lookup


def _resolve_section_paths(step_sections: list[str], document_id: str) -> list[str]:
    """
    Resolve guide section labels to concrete ``section_path`` payload values.

    Returns a deduplicated list of section titles suitable for Qdrant
    ``MatchAny`` filtering on the ``section_path`` payload field.
    """
    if not step_sections:
        return []

    lookup = _load_section_lookup(document_id)
    if not lookup:
        return list(dict.fromkeys(step_sections))

    resolved: list[str] = []
    for section in step_sections:
        norm = _normalize_section_name(section)
        if not norm:
            continue

        if norm in lookup:
            resolved.extend(lookup[norm])
            continue

        for known_norm, values in lookup.items():
            if norm in known_norm or known_norm in norm:
                resolved.extend(values)

    if not resolved:
        return list(dict.fromkeys(step_sections))

    return list(dict.fromkeys(resolved))


def _pick_chunk_level(question: str) -> str:
    """
    Use finer chunks for factual questions and coarser chunks for conceptual ones.
    """
    lowered = question.strip().lower()
    if any(lowered.startswith(prefix) for prefix in _FACTUAL_PREFIXES):
        return "fine"
    return "coarse"


def _result_score(result: Any) -> float:
    """Extract numeric score from RetrievalResult or dict."""
    score = getattr(result, "score", None)
    if score is None and isinstance(result, dict):
        score = result.get("score")
    try:
        return float(score)
    except Exception:  # noqa: BLE001
        return 0.0


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


def _result_to_dict(result: Any) -> dict[str, Any]:
    """Convert RetrievalResult-like objects to plain dicts for state output."""
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    return {
        "content": _result_content(result),
        "score": _result_score(result),
        "metadata": _result_metadata(result),
    }


def _is_reference_heading(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    heading = " ".join(value.split())
    if not heading:
        return False
    return bool(_REFERENCE_SECTION_HEADING_RE.match(heading))


def _is_reference_result(result: Any) -> bool:
    """Return True when chunk metadata indicates a references/bibliography section."""
    metadata = _result_metadata(result)

    if _is_reference_heading(metadata.get("section_title")):
        return True

    section_path = metadata.get("section_path")
    if isinstance(section_path, list):
        for item in section_path:
            if _is_reference_heading(item):
                return True
    elif _is_reference_heading(section_path):
        return True

    return False


def _dedupe_results(results: list[Any]) -> list[Any]:
    """Deduplicate retrieval hits by chunk_id (fallback: content prefix)."""
    best_by_key: dict[str, Any] = {}

    for result in results:
        metadata = _result_metadata(result)
        chunk_id = metadata.get("chunk_id")
        if chunk_id:
            key = f"id:{chunk_id}"
        else:
            key = f"text:{_result_content(result)[:200]}"

        existing = best_by_key.get(key)
        if existing is None or _result_score(result) > _result_score(existing):
            best_by_key[key] = result

    deduped = list(best_by_key.values())
    deduped.sort(key=_result_score, reverse=True)
    return deduped


def _dedupe_near_identical_chunks(
    chunks: list[Any],
    similarity_threshold: float = 0.7,
) -> list[Any]:
    """Deduplicate near-identical chunks using token-overlap Jaccard similarity."""
    deduped_chunks: list[Any] = []
    deduped_token_sets: list[set[str]] = []

    for chunk in chunks:
        chunk_tokens = set(_result_content(chunk).split())
        is_duplicate = False

        for kept_tokens in deduped_token_sets:
            union = chunk_tokens | kept_tokens
            if not union:
                jaccard = 1.0
            else:
                jaccard = len(chunk_tokens & kept_tokens) / len(union)

            if jaccard > similarity_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            deduped_chunks.append(chunk)
            deduped_token_sets.append(chunk_tokens)

    return deduped_chunks


def _build_qa_context(chunks: list[Any]) -> str:
    """Format chunk snippets into QA prompt context."""
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


def _is_rate_limit_exception(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "rate limit" in text
        or "rate_limit_exceeded" in text
        or "429" in text
        or "too many requests" in text
    )


def _build_extractive_fallback_answer(
    chunks: list[Any],
    max_chunks: int = 2,
    max_chars_per_chunk: int = 320,
) -> str:
    """Build a concise answer directly from retrieved chunks when LLM calls fail."""
    if not chunks:
        return "No relevant content found."

    parts = ["Generated using retrieved context (fallback mode):"]
    for idx, chunk in enumerate(chunks[:max_chunks], 1):
        metadata = _result_metadata(chunk)
        section_title = metadata.get("section_title")
        content = " ".join(_result_content(chunk).split())
        if len(content) > max_chars_per_chunk:
            content = content[:max_chars_per_chunk].rsplit(" ", 1)[0].rstrip() + "..."

        if isinstance(section_title, str) and section_title.strip():
            parts.append(f"{idx}. ({section_title.strip()}) {content}")
        else:
            parts.append(f"{idx}. {content}")

    return "\n".join(parts)


def _fallback_questions_for_label(label: str) -> list[str]:
    if label == "THEORETICAL":
        return [
            "What is the core theoretical problem addressed?",
            "What is the main proof strategy or formal argument?",
            "What assumptions and limitations are stated?",
            "What conclusions or open problems are highlighted?",
        ]
    if label == "SURVEY":
        return [
            "What is the scope of this survey?",
            "What taxonomy or categorization does the paper propose?",
            "What comparative findings are most important?",
            "What trends and future directions are identified?",
        ]

    # Default/APPLIED
    return [
        "What problem does this paper solve?",
        "What is the proposed method or model?",
        "What are the key experimental findings?",
        "What limitations or future work are discussed?",
    ]


def _build_fallback_guide_data(
    label: str,
    title: str,
    sections: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Create a deterministic structured guide when LLM guide generation is unavailable."""
    headings = [
        heading
        for heading in _flatten_section_headings(sections)
        if not _is_reference_heading(heading)
    ]

    if not headings:
        headings = ["Abstract", "Introduction", "Conclusion"]

    questions = _fallback_questions_for_label(label)
    question_section_pairs: list[dict[str, Any]] = []

    for idx, question in enumerate(questions):
        if idx == 0:
            scoped = headings[:2]
        elif idx == 1:
            scoped = headings[: min(4, len(headings))]
        elif idx == 2:
            scoped = headings[: min(6, len(headings))]
        else:
            scoped = headings[max(0, len(headings) - 3) :]

        scoped = list(dict.fromkeys(scoped))
        question_section_pairs.append(
            {
                "question": question,
                "sections": scoped,
                "needs_figures": False,
                "needs_tables": False,
            }
        )

    all_sections = list(
        dict.fromkeys(
            section
            for pair in question_section_pairs
            for section in pair.get("sections", [])
        )
    )

    def _mk_step(step_number: int, pair: dict[str, Any], objective: str, expected_output: str) -> dict[str, Any]:
        return {
            "step_number": step_number,
            "section_to_read": pair.get("sections", []),
            "needs_figures": bool(pair.get("needs_figures", False)),
            "needs_tables": bool(pair.get("needs_tables", False)),
            "objective": objective,
            "questions_to_answer": [pair.get("question", "")],
            "expected_output": expected_output,
        }

    fallback_title = (title or "").strip() or f"{label.title()} Paper"

    if label == "THEORETICAL":
        pass1_key, pass2_key, pass3_key = (
            "pass1_quick_scan",
            "pass2_proof_strategy",
            "pass3_deep_mathematical_analysis",
        )
        pass1_goal = "Understand the theorem-level claims and problem framing without reading proofs in detail."
        pass2_goal = "Identify assumptions, proof strategy, and key intermediate results."
        pass3_goal = "Read proof details, implications, and open theoretical directions."
        reflection_questions = [
            "Which assumptions are most critical for the main results?",
            "How does the proof strategy compare to related theoretical techniques?",
            "What open problems naturally follow from these results?",
        ]
    elif label == "SURVEY":
        pass1_key, pass2_key, pass3_key = (
            "pass1_field_overview",
            "pass2_taxonomy_understanding",
            "pass3_research_landscape_analysis",
        )
        pass1_goal = "Map the survey scope, motivation, and major categories."
        pass2_goal = "Understand taxonomy criteria and category-level comparisons."
        pass3_goal = "Synthesize trends, gaps, and promising future directions."
        reflection_questions = [
            "Which taxonomy dimensions are most actionable for your use case?",
            "Which categories appear under-explored and why?",
            "What concrete follow-up papers should be prioritized next?",
        ]
    else:
        pass1_key, pass2_key, pass3_key = (
            "pass1_quick_scan",
            "pass2_method_understanding",
            "pass3_deep_analysis",
        )
        pass1_goal = "Understand problem, motivation, and high-level contribution."
        pass2_goal = "Understand method design and experimental setup."
        pass3_goal = "Validate claims via detailed results, limitations, and failure modes."
        reflection_questions = [
            "Which design choices seem most responsible for the reported gains?",
            "What evidence best supports the paper's central claim?",
            "What limitations matter most for real-world use?",
        ]

    pass1_steps = [
        _mk_step(
            1,
            question_section_pairs[0],
            "Get a fast global understanding of the paper.",
            "A concise summary of the main problem and contribution.",
        )
    ]
    pass2_steps = [
        _mk_step(
            1,
            question_section_pairs[1],
            "Understand how the core approach/argument is built.",
            "A clear outline of the method/proof strategy and assumptions.",
        )
    ]
    pass3_steps = [
        _mk_step(
            1,
            question_section_pairs[2],
            "Inspect evidence depth, technical details, and limitations.",
            "A judgment on the strength and boundaries of the claims.",
        ),
        _mk_step(
            2,
            question_section_pairs[3],
            "Extract future work and unresolved questions.",
            "A short list of follow-up research questions.",
        ),
    ]

    guide_json: dict[str, Any] = {
        "paper_title": fallback_title,
        "reading_strategy": {
            "method": "three_pass_method",
            "paper_type": label.lower(),
            "estimated_total_time": "45-60 minutes",
        },
        pass1_key: {
            "goal": pass1_goal,
            "estimated_time": "10-15 minutes",
            "steps": pass1_steps,
        },
        pass2_key: {
            "goal": pass2_goal,
            "estimated_time": "15-20 minutes",
            "steps": pass2_steps,
        },
        pass3_key: {
            "goal": pass3_goal,
            "estimated_time": "20-25 minutes",
            "steps": pass3_steps,
        },
        "final_user_task": {
            "summary_task": "Write a one-page synthesis covering core claims, evidence strength, and practical implications.",
            "reflection_questions": reflection_questions,
        },
        "fallback": True,
        "category": label,
        "notes": "Heuristic fallback guide generated because LLM guide generation was unavailable.",
    }

    return guide_json, question_section_pairs, all_sections


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def extraction_node(state: dict) -> dict:
    """
    Extract metadata and content from PDF.
    
    Entry point for the workflow when starting from a PDF file.
    """
    logger.info("🔍 Extraction node: processing PDF...")
    
    pdf_path = state.get("pdf_path")
    if not pdf_path:
        return {
            **state,
            "errors": [*state.get("errors", []), "No pdf_path provided for extraction"],
        }
    
    force_ocr = state.get("force_ocr", False)
    
    try:
        # Get Groq API key from environment (needed for extraction metadata LLM)
        from config import GROQ_API_KEY
        extractor = PDFExtractor(groq_api_key=GROQ_API_KEY)
        
        # Run extraction
        result = extractor.extract(
            pdf_path=pdf_path,
            output_dir=Path("output"),
            force_ocr=force_ocr,
            save_metadata_file=False,
            save_fulltext_file=False,
        )
        
        # Map extraction results to state
        metadata = result["metadata"]
        return {
            **state,
            "document_id": result["document_id"],
            "full_text": result["full_text"],
            "title": metadata.get("paper_title", ""),
            "abstract": metadata.get("abstract", ""),
            "sections": metadata.get("sections", []),
            "hierarchy": result["hierarchy"],
            "extraction_files": result.get("files", {}),
        }
        
    except Exception as exc:
        logger.error(f"Extraction failed: {exc}")
        return {
            **state,
            "errors": [*state.get("errors", []), f"Extraction error: {exc}"],
        }


def categorizer_node(state: dict) -> dict:
    """
    Classify the paper into one of five categories.
    
    Uses title and abstract extracted in previous step.
    """
    logger.info("📚 Categorizer node: classifying paper...")
    
    title = state.get("title", "").strip()
    abstract = state.get("abstract", "").strip()
    
    if not title or not abstract:
        return {
            **state,
            "errors": [*state.get("errors", []), "Missing title or abstract for categorization"],
            "confidence": "LOW",
        }
    
    try:
        llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
        prompt = categorizer_prompt(title=title, abstract=abstract)
        response = llm.invoke([HumanMessage(content=prompt)])
        
        # Extract JSON from response
        parsed = _extract_json(response.content)
        
        category = parsed.get("category", "").strip().upper()
        confidence = parsed.get("confidence", "").strip().upper()
        reasoning = parsed.get("reasoning", "").strip()
        
        # Validate category
        valid_categories = {
            "APPLIED",
            "THEORETICAL",
            "SURVEY",
        }
        if category not in valid_categories:
            logger.warning(f"Invalid category: {category}")
            category = None
        
        # Validate confidence
        valid_confidence = {"HIGH", "MEDIUM", "LOW"}
        if confidence not in valid_confidence:
            confidence = "LOW"
        
        return {
            **state,
            "category": category,
            "confidence": confidence,
            "category_reasoning": reasoning,
        }
        
    except Exception as exc:
        logger.error(f"Categorization failed: {exc}")
        return {
            **state,
            "errors": [*state.get("errors", []), f"Categorization error: {exc}"],
            "confidence": "LOW",
        }


def _retrieve_for_question(
    pipeline,
    question: str,
    step_sections: list[str],
    document_id: str,
) -> tuple[list[Any], dict[str, Any]]:
    """
    Run section-aware retrieval for one question and return reranked hits.

    Flow:
            1. Use the original question as the retrieval query.
            2. Run scoped retrieval against resolved ``section_path`` values.
            3. If scoped recall is low, run a smaller unrestricted fallback.
            4. Merge + deduplicate candidates, then rerank once.
    """
        base_question = question.strip()
        if not base_question:
                return [], {
                        "expanded_queries": [],
                        "resolved_sections": _resolve_section_paths(step_sections, document_id),
                        "chunk_level": _pick_chunk_level(question),
                }

        expanded_queries = [base_question]
    chunk_level = _pick_chunk_level(question)
    resolved_sections = _resolve_section_paths(step_sections, document_id)

    scoped_hits: list[Any] = []
    for expanded_query in expanded_queries:
        scoped_hits.extend(
            pipeline.query(
                query=expanded_query,
                document_id=document_id or None,
                section_path_any=resolved_sections or None,
                chunk_level=chunk_level,
                top_k=SCOPED_TOP_K,
                top_n=SCOPED_TOP_K,
                rerank=False,
            )
        )

    merged_hits = _dedupe_results(scoped_hits)

    # If scoped pass under-recovers, add a smaller unrestricted pass.
    if len(merged_hits) < 3:
        fallback_hits: list[Any] = []
        for expanded_query in expanded_queries:
            fallback_hits.extend(
                pipeline.query(
                    query=expanded_query,
                    document_id=document_id or None,
                    chunk_level=chunk_level,
                    top_k=FALLBACK_TOP_K,
                    top_n=FALLBACK_TOP_K,
                    rerank=False,
                )
            )
        merged_hits = _dedupe_results(merged_hits + fallback_hits)

    # Backward-compatibility: old indexes do not have ``chunk_level`` payload.
    # Retry without chunk filtering if nothing was retrieved.
    if not merged_hits:
        compatibility_hits: list[Any] = []
        for expanded_query in expanded_queries:
            compatibility_hits.extend(
                pipeline.query(
                    query=expanded_query,
                    document_id=document_id or None,
                    section_path_any=resolved_sections or None,
                    top_k=SCOPED_TOP_K,
                    top_n=SCOPED_TOP_K,
                    rerank=False,
                )
            )

        if len(compatibility_hits) < 3:
            for expanded_query in expanded_queries:
                compatibility_hits.extend(
                    pipeline.query(
                        query=expanded_query,
                        document_id=document_id or None,
                        top_k=FALLBACK_TOP_K,
                        top_n=FALLBACK_TOP_K,
                        rerank=False,
                    )
                )

        merged_hits = _dedupe_results(compatibility_hits)

    rerank_budget = max(RERANKER_TOP_N, SCOPED_TOP_K + FALLBACK_TOP_K)
    rerank_input = merged_hits[:rerank_budget]
    reranked_hits = pipeline.rerank_results(
        query=question,
        results=rerank_input,
        top_n=RERANKER_TOP_N,
    )

    reranked_hits = [hit for hit in reranked_hits if not _is_reference_result(hit)]

    return reranked_hits, {
        "expanded_queries": expanded_queries,
        "resolved_sections": resolved_sections,
        "chunk_level": chunk_level,
    }


def retrieve_and_qa_node(state: dict) -> dict:
    """
    Parallel retrieve-then-answer loop for guide questions.

    Per question:
            1. Retrieve with the original question and section scope.
            2. Run fallback retrieval when scoped recall is low.
            3. Rerank once and answer from top-K chunks.

    Questions are processed in parallel to reduce end-to-end latency.
    """
    logger.info("🔎💬 Retrieve-and-QA node: parallel retrieve → answer loop…")

    question_section_pairs = state.get("question_section_pairs") or []
    user_query = (state.get("query") or "").strip()
    document_id = state.get("document_id", "")

    # Build candidate pairs (guide questions preferred, direct query as fallback)
    if question_section_pairs:
        all_pairs = question_section_pairs
    elif user_query:
        all_pairs = [{"question": user_query, "sections": []}]
    else:
        logger.warning("No guide questions or direct query available; skipping retrieval")
        return {
            **state,
            "per_question_results": state.get("per_question_results") or [],
            "retrieval_results": state.get("retrieval_results") or [],
            "qa_results": state.get("qa_results") or [],
        }

    # Process a bounded number of questions for latency control.
    pairs = all_pairs[:MAX_GUIDE_QUESTIONS]

    try:
        # ── Index document once before question processing ───────────────────
        pipeline = _get_retrieval_pipeline()

        if document_id:
            hierarchy_path = Path("output") / f"{document_id}_hierarchy.json"
            if hierarchy_path.exists():
                pdf_path_value = state.get("pdf_path")
                pdf_path_obj: Path | None = None
                if pdf_path_value:
                    candidate_pdf = Path(pdf_path_value)
                    if candidate_pdf.exists():
                        pdf_path_obj = candidate_pdf
                index_result = pipeline.index(
                    hierarchy_json_path=hierarchy_path,
                    output_dir=Path("output"),
                    pdf_path=pdf_path_obj,
                )
                if not index_result.skipped:
                    logger.info(
                        "Indexed %d chunks for document %s",
                        index_result.total_chunks,
                        document_id,
                    )
            else:
                logger.warning(
                    "Hierarchy file not found for document %s; skipping indexing",
                    document_id,
                )

        total_questions = len(pairs)
        workers = max(1, min(total_questions, MAX_PARALLEL_QUESTIONS))
        logger.info(
            "Processing %d question(s) (of %d total) — parallel retrieve→answer with %d workers",
            total_questions,
            len(all_pairs),
            workers,
        )

        metadata = {
            "paper_title": state.get("title", ""),
            "category": state.get("category", ""),
        }
        rate_limit_event = threading.Event()

        def _process_single_question(idx: int, pair: dict) -> tuple[int, dict, dict]:
            question = pair["question"]
            step_sections: list[str] = pair.get("sections") or []
            needs_figures = bool(pair.get("needs_figures", False))
            needs_tables = bool(pair.get("needs_tables", False))

            logger.info(
                "  [%d/%d] Retrieving for: %s…  sections=%s",
                idx,
                total_questions,
                question[:70],
                step_sections,
            )

            hits, retrieval_meta = _retrieve_for_question(
                pipeline=pipeline,
                question=question,
                step_sections=step_sections,
                document_id=document_id,
            )

            # Optionally include figure/table chunks scoped to the same step sections.
            if document_id and (needs_figures or needs_tables):
                for section_id in step_sections:
                    if needs_figures:
                        figure_chunks = pipeline.retrieve_by_content_type(
                            document_id=document_id,
                            section_id=section_id,
                            content_type="figure",
                            top_k=5,
                        )
                        hits.extend(figure_chunks)

                    if needs_tables:
                        table_chunks = pipeline.retrieve_by_content_type(
                            document_id=document_id,
                            section_id=section_id,
                            content_type="table",
                            top_k=5,
                        )
                        hits.extend(table_chunks)

            hits = _dedupe_results(hits)
            hits = [chunk for chunk in hits if not _is_reference_result(chunk)]
            filtered_hits = [
                chunk for chunk in hits if _result_score(chunk) >= MIN_RELEVANCE_THRESHOLD
            ]
            if len(filtered_hits) < 2:
                filtered_hits = hits[:2]

            deduped_hits = _dedupe_near_identical_chunks(filtered_hits)
            top_hits = deduped_hits[:QA_TOP_K]
            logger.info(
                "      → %d chunks retrieved, using top %d",
                len(hits),
                len(top_hits),
            )

            per_question_result = {
                "question": question,
                "sections": step_sections,
                "resolved_sections": retrieval_meta["resolved_sections"],
                "expanded_queries": retrieval_meta["expanded_queries"],
                "chunk_level": retrieval_meta["chunk_level"],
                "chunks": [_result_to_dict(r) for r in hits],
            }

            # Step 2 — Answer
            if not top_hits:
                logger.warning("    No chunks for Q%d — skipping LLM call", idx)
                return idx, per_question_result, {
                    "question": question,
                    "answer": "No relevant content found.",
                    "confidence": "LOW",
                }

            context = _build_qa_context(top_hits)
            if not context.strip():
                logger.warning("    No non-reference context for Q%d — using fallback", idx)
                return idx, per_question_result, {
                    "question": question,
                    "answer": _build_extractive_fallback_answer(top_hits),
                    "confidence": "LOW",
                }

            if rate_limit_event.is_set():
                logger.warning(
                    "    Rate-limit fallback active for Q%d — skipping LLM call",
                    idx,
                )
                return idx, per_question_result, {
                    "question": question,
                    "answer": _build_extractive_fallback_answer(top_hits),
                    "confidence": "LOW",
                }

            logger.info("      → Generating answer for Q%d…", idx)
            try:
                llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)
                prompt = qa_prompt(query=question, context=context, metadata=metadata)
                response = llm.invoke([HumanMessage(content=prompt)])
                answer = response.content.strip()
                confidence = "HIGH" if len(answer) > 100 else "MEDIUM"
            except Exception as exc:
                if _is_rate_limit_exception(exc):
                    rate_limit_event.set()
                    logger.warning(
                        "    LLM rate-limited for Q%d; using extractive fallback answer",
                        idx,
                    )
                    answer = _build_extractive_fallback_answer(top_hits)
                else:
                    logger.error("    LLM call failed for Q%d: %s", idx, exc)
                    answer = "An error occurred while generating the answer."
                confidence = "LOW"

            logger.info("      ✓ Q%d answered (confidence=%s)", idx, confidence)
            return idx, per_question_result, {
                "question": question,
                "answer": answer,
                "confidence": confidence,
            }

        ordered_results: dict[int, tuple[dict, dict]] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_process_single_question, idx, pair): idx
                for idx, pair in enumerate(pairs, 1)
            }

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    out_idx, per_question_result, qa_result = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.error("Question %d failed: %s", idx, exc, exc_info=True)
                    failed_pair = pairs[idx - 1]
                    out_idx = idx
                    per_question_result = {
                        "question": failed_pair.get("question", ""),
                        "sections": failed_pair.get("sections") or [],
                        "resolved_sections": [],
                        "expanded_queries": [failed_pair.get("question", "")],
                        "chunk_level": "coarse",
                        "chunks": [],
                    }
                    qa_result = {
                        "question": failed_pair.get("question", ""),
                        "answer": "An error occurred while generating the answer.",
                        "confidence": "LOW",
                    }

                ordered_results[out_idx] = (per_question_result, qa_result)

        per_question_results: list[dict] = []
        qa_results: list[dict] = []
        for idx in range(1, total_questions + 1):
            if idx not in ordered_results:
                continue
            per_question_result, qa_result = ordered_results[idx]
            per_question_results.append(per_question_result)
            qa_results.append(qa_result)

        retrieval_queries: list[str] = []
        for per_question_result in per_question_results:
            expanded_queries = per_question_result.get("expanded_queries") or []
            if expanded_queries:
                retrieval_queries.append(expanded_queries[0])
            elif per_question_result.get("question"):
                retrieval_queries.append(per_question_result["question"])
        retrieval_queries = list(dict.fromkeys(retrieval_queries))

        logger.info("Retrieve-and-QA complete: %d answers generated", len(qa_results))
        return {
            **state,
            "per_question_results": per_question_results,
            "retrieval_results": [
                c for qr in per_question_results for c in qr["chunks"][:QA_TOP_K]
            ],
            "retrieval_query": retrieval_queries[0] if retrieval_queries else None,
            "retrieval_queries": retrieval_queries or None,
            "qa_results": qa_results,
        }

    except Exception as exc:
        logger.error("Retrieve-and-QA failed: %s", exc, exc_info=True)
        return {
            **state,
            "errors": [*state.get("errors", []), f"Retrieve-and-QA error: {exc}"],
        }


def summarizer_node(state: dict) -> dict:
    """
    Generate a structured summary of the paper.
    
    Alternative to Q&A when no query is provided.
    """
    logger.info("📝 Summarizer node: generating summary...")
    
    title = state.get("title", "")
    abstract = state.get("abstract", "")
    sections = state.get("sections", [])
    category = state.get("category", "APPLIED")
    
    if not title or not abstract:
        return {
            **state,
            "errors": [*state.get("errors", []), "Missing title or abstract for summarization"],
        }
    
    try:
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)
        prompt = summarizer_prompt(
            title=title,
            abstract=abstract,
            sections=sections,
            category=category
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        
        summary = response.content.strip()
        
        # Simple extraction of key contributions (look for numbered list)
        contributions = []
        lines = summary.split("\n")
        for line in lines:
            if re.match(r"^\d+\.", line.strip()):
                contributions.append(line.strip())
        
        return {
            **state,
            "summary": summary,
            "key_contributions": contributions if contributions else None,
        }
        
    except Exception as exc:
        logger.error(f"Summarization failed: {exc}")
        return {
            **state,
            "errors": [*state.get("errors", []), f"Summarization error: {exc}"],
        }


def _run_guide_node(
    state: dict,
    label: str,
    guide_model_cls,
    prompt_fn,
) -> dict:
    """
    Generic helper called by all three guide nodes.

    Parameters
    ----------
    state         : current workflow state
    label         : human-readable label for logging (e.g. "APPLIED")
    guide_model_cls : Pydantic model class for structured output
    prompt_fn     : function(title, abstract, sections, num_figures, num_tables[, introduction, conclusion]) → str
    """
    logger.info("📖 Guide node [%s]: generating reading guide…", label)

    title = state.get("title", "")
    abstract = state.get("abstract", "")
    sections = state.get("sections") or []
    full_text = state.get("full_text", "")
    document_id = state.get("document_id", "")

    if not title or not abstract:
        return {
            **state,
            "errors": [*state.get("errors", []), f"Missing title or abstract for {label} guide"],
        }

    try:
        num_figures = sum(s.get("stats", {}).get("figures", 0) for s in sections)
        num_tables = sum(s.get("stats", {}).get("tables", 0) for s in sections)

        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1)
        structured_llm = llm.with_structured_output(guide_model_cls)

        prompt_kwargs = {
            "title": title,
            "abstract": abstract,
            "sections": sections,
            "num_figures": num_figures,
            "num_tables": num_tables,
        }

        prompt_parameters = inspect.signature(prompt_fn).parameters
        if "introduction" in prompt_parameters or "conclusion" in prompt_parameters:
            introduction, conclusion = _extract_intro_conclusion_context(
                full_text=full_text,
                sections=sections,
            )
            if "introduction" in prompt_parameters:
                prompt_kwargs["introduction"] = introduction
            if "conclusion" in prompt_parameters:
                prompt_kwargs["conclusion"] = conclusion

        prompt = prompt_fn(**prompt_kwargs)

        guide_model = structured_llm.invoke(prompt)
        guide_json = guide_model.model_dump()

        # Extract per-question (question, step_sections) pairs from the guide
        question_section_pairs = _extract_guide_retrieval_info(guide_json)
        # Flat lists kept for display / backward compat
        questions = [p["question"] for p in question_section_pairs]
        all_sections = list(dict.fromkeys(s for p in question_section_pairs for s in p["sections"]))
        logger.info(
            "Guide [%s]: extracted %d questions across %d unique sections for retrieval",
            label, len(questions), len(all_sections),
        )

        # Persist guide to disk
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        guide_path = output_dir / f"{document_id}_guide.json"
        with open(guide_path, "w", encoding="utf-8") as f:
            json.dump(guide_json, f, indent=2, ensure_ascii=False)
        logger.info("✅ Reading guide saved to: %s", guide_path)

        return {
            **state,
            "reading_guide": guide_json,
            "guide_file_path": str(guide_path),
            "question_section_pairs": question_section_pairs,
            # Flat versions kept for display
            "questions_to_answer": questions,
            "sections_to_read": all_sections,
        }

    except Exception as exc:
        if _is_rate_limit_exception(exc):
            logger.warning(
                "Guide generation [%s] rate-limited; using heuristic fallback guide",
                label,
            )

            guide_json, question_section_pairs, all_sections = _build_fallback_guide_data(
                label=label,
                title=title,
                sections=sections,
            )
            questions = [p["question"] for p in question_section_pairs]

            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)
            guide_path = output_dir / f"{document_id}_guide.json"
            with open(guide_path, "w", encoding="utf-8") as f:
                json.dump(guide_json, f, indent=2, ensure_ascii=False)

            return {
                **state,
                "reading_guide": guide_json,
                "guide_file_path": str(guide_path),
                "question_section_pairs": question_section_pairs,
                "questions_to_answer": questions,
                "sections_to_read": all_sections,
            }

        logger.error("Guide generation [%s] failed: %s", label, exc)
        return {
            **state,
            "errors": [*state.get("errors", []), f"Guide generation error [{label}]: {exc}"],
        }


def applied_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for APPLIED papers."""
    return _run_guide_node(
        state,
        label="APPLIED",
        guide_model_cls=AppliedReadingGuide,
        prompt_fn=applied_guide_prompt,
    )


def theoretical_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for THEORETICAL papers."""
    return _run_guide_node(
        state,
        label="THEORETICAL",
        guide_model_cls=TheoreticalReadingGuide,
        prompt_fn=theoretical_guide_prompt,
    )


def survey_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for SURVEY papers."""
    return _run_guide_node(
        state,
        label="SURVEY",
        guide_model_cls=SurveyReadingGuide,
        prompt_fn=survey_guide_prompt,
    )



# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------

# Category → guide node name mapping (used in routing and graph wiring)
_CATEGORY_GUIDE_NODE = {
    "APPLIED": "applied_guide",
    "THEORETICAL": "theoretical_guide",
    "SURVEY": "survey_guide",
}


def route_after_categorizer(state: dict) -> str:
    """
    Route after categorization.

    Routing logic (no query path — generate reading guide based on category):
    - APPLIED      → applied_guide
    - THEORETICAL  → theoretical_guide
    - SURVEY       → survey_guide

    If a user query is provided directly → retrieve_and_qa (skip guide generation).
    """
    query = (state.get("query") or "").strip()
    category = state.get("category", "")

    # If user provided a direct query, go straight to retrieve_and_qa (skip guide)
    if query:
        logger.info("→ Routing to retrieve_and_qa (direct query path — skip guide)")
        return "retrieve_and_qa"

    # Route to the appropriate category-specific guide node
    guide_node = _CATEGORY_GUIDE_NODE.get(category)
    if guide_node:
        logger.info("→ Routing to %s (category=%s)", guide_node, category)
        return guide_node

    # Fallback: summarize if category unknown
    logger.info("→ Routing to summarizer (fallback: unknown category %s)", category)
    return "summarizer"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph():
    """
    Build and compile the LangGraph pipeline.

    Workflow paths
    --------------
    Guide path (no user query — default):
        START → extraction → categorizer → <category_guide> → retrieve_and_qa → END

    Direct query path (user provides a query, guide skipped):
        START → extraction → categorizer → retrieve_and_qa → END

    Summarizer fallback (unknown category):
        START → extraction → categorizer → summarizer → END

    Guide nodes (one per category):
        applied_guide     (APPLIED)
        theoretical_guide (THEORETICAL)
        survey_guide      (SURVEY)

    Returns:
        A compiled LangGraph CompiledGraph ready for invocation.
    """
    builder = StateGraph(dict)

    # ── Nodes ──────────────────────────────────────────────────────────────
    builder.add_node("extraction", extraction_node)
    builder.add_node("categorizer", categorizer_node)

    # Three category-specific guide nodes
    builder.add_node("applied_guide", applied_guide_node)
    builder.add_node("theoretical_guide", theoretical_guide_node)
    builder.add_node("survey_guide", survey_guide_node)

    # Shared downstream nodes
    builder.add_node("retrieve_and_qa", retrieve_and_qa_node)
    builder.add_node("summarizer", summarizer_node)

    # ── Edges ──────────────────────────────────────────────────────────────
    builder.add_edge(START, "extraction")
    builder.add_edge("extraction", "categorizer")

    # Conditional routing: categorizer → one of the 3 guide nodes, retrieve_and_qa, or summarizer
    builder.add_conditional_edges(
        "categorizer",
        route_after_categorizer,
        {
            "applied_guide": "applied_guide",
            "theoretical_guide": "theoretical_guide",
            "survey_guide": "survey_guide",
            "retrieve_and_qa": "retrieve_and_qa",
            "summarizer": "summarizer",
        },
    )

    # All three guide nodes flow into the combined retrieve-and-QA node
    for guide_node in _CATEGORY_GUIDE_NODE.values():
        builder.add_edge(guide_node, "retrieve_and_qa")

    # Summarizer and retrieve-and-QA paths both terminate
    builder.add_edge("summarizer", END)
    builder.add_edge("retrieve_and_qa", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------

_agent = None


def get_agent():
    """
    Return a lazily-initialized compiled agent with LangSmith tracing enabled.
    
    This constructs the graph and configures LangSmith on first call.
    The agent is cached for subsequent calls.
    """
    global _agent
    if _agent is not None:
        return _agent
    
    # Load environment variables
    load_dotenv()
    
    # Configure LangSmith tracing
    langsmith_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    if langsmith_enabled:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = os.getenv(
            "LANGCHAIN_ENDPOINT",
            "https://api.smith.langchain.com"
        )
        os.environ["LANGCHAIN_PROJECT"] = os.getenv(
            "LANGCHAIN_PROJECT",
            "ResearchPaperAssistant"
        )
        api_key = os.getenv("LANGCHAIN_API_KEY")
        if api_key:
            os.environ["LANGCHAIN_API_KEY"] = api_key
            logger.info("✅ LangSmith tracing enabled")
        else:
            logger.warning("⚠️  LANGCHAIN_TRACING_V2=true but LANGCHAIN_API_KEY not set")
    else:
        logger.info("LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true to enable)")
    
    # Build and cache the graph
    logger.info("Building research paper assistant graph...")
    _agent = build_graph()
    logger.info("✅ Graph compiled and ready")
    
    return _agent
