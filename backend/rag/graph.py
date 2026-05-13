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

try:
    from langsmith.run_helpers import traceable, get_current_run_tree
except Exception:  # noqa: BLE001
    # Keep graph execution functional when LangSmith is not installed.
    def traceable(*_args, **_kwargs):
        def _decorator(func):
            return func

        return _decorator

from config import MIN_RELEVANCE_THRESHOLD
from rag.states import AgentState, RetrievalResult
from rag.prompts import (
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
from rag.tfidf_categorizer import TfidfPaperCategorizer
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

_GUIDE_PASS_KEYS = (
    "pass1_quick_scan",
    "pass2_method_understanding",
    "pass3_deep_analysis",
    "pass1_field_overview",
    "pass2_taxonomy_understanding",
    "pass3_research_landscape_analysis",
    "pass2_proof_strategy",
    "pass3_deep_mathematical_analysis",
)
_GUIDE_VALIDATION_ATTEMPTS = 2
_GUIDE_MAX_SECTIONS_PER_STEP = 3
_ABSTRACT_HEADING = "Abstract"
_MIN_QUESTIONS_PER_STEP = 1
_MAX_QUESTIONS_PER_STEP = 2

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

    for key in _GUIDE_PASS_KEYS:
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
_tfidf_categorizer: TfidfPaperCategorizer | None = None


def _get_retrieval_pipeline():
    """Return a process-wide RetrievalPipeline singleton."""
    global _retrieval_pipeline
    if _retrieval_pipeline is None:
        from rag.retrieval.pipeline import get_retrieval_pipeline

        _retrieval_pipeline = get_retrieval_pipeline()
    return _retrieval_pipeline


def _get_tfidf_categorizer() -> TfidfPaperCategorizer:
    """Return a process-wide TF-IDF categorizer singleton."""
    global _tfidf_categorizer
    if _tfidf_categorizer is None:
        _tfidf_categorizer = TfidfPaperCategorizer()
    return _tfidf_categorizer

# Import extraction orchestrator
import sys
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from backend.extraction.extraction import PDFExtractor

logger = logging.getLogger(__name__)


def _normalize_category_label(label: str) -> str | None:
    """Normalize model-predicted labels to canonical category names."""
    normalized = (label or "").strip().upper()
    if normalized in {"APPLIED", "THEORETICAL", "SURVEY"}:
        return normalized

    alias_map = {
        "APPLICATION": "APPLIED",
        "EMPIRICAL": "APPLIED",
        "REVIEW": "SURVEY",
        "LITERATURE REVIEW": "SURVEY",
        "THEORY": "THEORETICAL",
    }
    return alias_map.get(normalized)


def _confidence_from_probability(probability: float) -> str:
    """Convert top-class probability into workflow confidence buckets."""
    if probability >= 0.75:
        return "HIGH"
    if probability >= 0.45:
        return "MEDIUM"
    return "LOW"


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

_TRACE_CHAT_CHUNK_PREVIEW_COUNT = 8
_TRACE_CHAT_CHUNK_TEXT_CHARS = 320
_CHAT_TRACE_RUNNER_CACHE: dict[str, Any] = {}


def _safe_chat_trace_stage_name(stage: str) -> str:
    """Normalize stage names for stable LangSmith node labels."""
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(stage).strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unknown"


def _trace_chat_retrieval_stage(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Emit a stage-specific LangSmith child run for chat retrieval internals."""
    safe_stage = _safe_chat_trace_stage_name(stage)
    runner = _CHAT_TRACE_RUNNER_CACHE.get(safe_stage)
    if runner is None:
        @traceable(name=f"chat_retrieval_stage:{safe_stage}", run_type="chain")
        def _runner(event_payload: dict[str, Any]) -> dict[str, Any]:
            return event_payload

        runner = _runner
        _CHAT_TRACE_RUNNER_CACHE[safe_stage] = runner

    return runner({"stage": stage, **payload})





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


def _flatten_leaf_section_headings(sections: list[dict[str, Any]] | None) -> list[str]:
    """Return only leaf-level section headings in source order."""
    if not sections:
        return []

    leaves: list[str] = []
    seen: set[str] = set()

    def _walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue

            children = node.get("sections")
            if isinstance(children, list) and children:
                _walk(children)
                continue

            heading = str(node.get("original_name") or node.get("title") or "").strip()
            if heading and heading not in seen:
                seen.add(heading)
                leaves.append(heading)

    _walk(sections)
    return leaves


def _iter_guide_passes(guide_json: dict[str, Any]):
    """Yield guide pass key and pass dict for known pass keys present in output."""
    for pass_key in _GUIDE_PASS_KEYS:
        pass_payload = guide_json.get(pass_key)
        if isinstance(pass_payload, dict):
            yield pass_key, pass_payload


def _iter_guide_steps(guide_json: dict[str, Any]):
    """Yield (pass_key, pass_payload, step_payload) for all known guide pass steps."""
    for pass_key, pass_payload in _iter_guide_passes(guide_json):
        steps = pass_payload.get("steps") or []
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict):
                yield pass_key, pass_payload, step


def _normalize_id_list(values: Any) -> list[str]:
    """Normalize arbitrary value into a de-duplicated list of non-empty strings."""
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        # Convert to string (handles int, float, etc.) and strip whitespace
        str_value = str(value).strip() if value is not None else ""
        if not str_value or str_value in seen:
            continue
        seen.add(str_value)
        normalized.append(str_value)
    return normalized


def _strip_image_data_uri(text: str, max_chars: int = 600) -> str:
    """Remove large inline image payloads and keep concise text for prompts."""
    if not isinstance(text, str):
        return ""
    cleaned = re.sub(r"!\[Image\]\(data:image/[^)]*\)", "", text)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rsplit(" ", 1)[0].rstrip() + "..."


def _extract_visual_context(document_id: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
    """Collect section->visual ID mapping and concise figure/table summaries from complete extraction output."""
    section_visual_map: dict[str, dict[str, list[str]]] = {}
    available_figure_ids: list[str] = []
    available_table_ids: list[str] = []
    figure_summaries: dict[str, str] = {}
    table_summaries: dict[str, str] = {}

    for section in _flatten_section_headings(sections):
        section_visual_map[section] = {"figure_ids": [], "table_ids": []}

    complete_path = Path("output") / f"{document_id}_complete.json"
    if not complete_path.exists():
        return {
            "available_figure_ids": available_figure_ids,
            "available_table_ids": available_table_ids,
            "section_visual_map": section_visual_map,
            "figure_summaries": figure_summaries,
            "table_summaries": table_summaries,
        }

    try:
        with complete_path.open("r", encoding="utf-8") as fh:
            complete = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse visual context from %s: %s", complete_path, exc)
        return {
            "available_figure_ids": available_figure_ids,
            "available_table_ids": available_table_ids,
            "section_visual_map": section_visual_map,
            "figure_summaries": figure_summaries,
            "table_summaries": table_summaries,
        }

    metadata_sections = (
        (complete.get("metadata") or {}).get("sections")
        if isinstance(complete, dict)
        else []
    ) or []

    for node in metadata_sections:
        if not isinstance(node, dict):
            continue
        section_name = str(node.get("original_name") or node.get("title") or "").strip()
        if not section_name:
            continue
        stats = node.get("stats") or {}
        figure_ids = _normalize_id_list(stats.get("figure_ids"))
        table_ids = _normalize_id_list(stats.get("table_ids"))
        if section_name not in section_visual_map:
            section_visual_map[section_name] = {"figure_ids": [], "table_ids": []}
        section_visual_map[section_name]["figure_ids"] = figure_ids
        section_visual_map[section_name]["table_ids"] = table_ids

    extracted_elements = complete.get("extracted_elements") if isinstance(complete, dict) else {}
    figures = (extracted_elements or {}).get("figures") or []
    tables = (extracted_elements or {}).get("tables") or []

    for figure in figures:
        if not isinstance(figure, dict):
            continue
        fig_id = str(figure.get("id") or "").strip()
        if not fig_id:
            continue
        if fig_id not in available_figure_ids:
            available_figure_ids.append(fig_id)
        summary = _strip_image_data_uri(str(figure.get("caption") or figure.get("text") or ""))
        if summary:
            figure_summaries[fig_id] = summary

    for table in tables:
        if not isinstance(table, dict):
            continue
        table_id = str(table.get("id") or "").strip()
        if not table_id:
            continue
        if table_id not in available_table_ids:
            available_table_ids.append(table_id)
        summary = _strip_image_data_uri(str(table.get("text") or table.get("markdown") or ""))
        if summary:
            table_summaries[table_id] = summary

    return {
        "available_figure_ids": available_figure_ids,
        "available_table_ids": available_table_ids,
        "section_visual_map": section_visual_map,
        "figure_summaries": figure_summaries,
        "table_summaries": table_summaries,
    }


def _ensure_step_questions(step: dict[str, Any]) -> None:
    """Ensure each step has 1-2 simple, section-specific questions."""
    questions = step.get("questions_to_answer")
    if not isinstance(questions, list):
        questions = []

    cleaned = [q.strip() for q in questions if isinstance(q, str) and q.strip()]
    if cleaned:
        step["questions_to_answer"] = cleaned[:_MAX_QUESTIONS_PER_STEP]
        return

    sections = step.get("section_to_read") or []
    section_label = sections[0] if sections else "this section"
    objective = str(step.get("objective") or "").strip()
    expected = str(step.get("expected_output") or "").strip()

    fallback = [
        f"What is the main takeaway from {section_label}?",
    ]
    if objective:
        fallback.append(f"How does {section_label} help with: {objective}?")
    elif expected:
        fallback.append(f"What should you be able to explain after reading {section_label}?")

    step["questions_to_answer"] = fallback[:_MAX_QUESTIONS_PER_STEP]


def _normalize_guide_steps(
    guide_json: dict[str, Any],
    section_visual_map: dict[str, dict[str, list[str]]],
) -> dict[str, Any]:
    """Normalize step sections, visual IDs, and ensure simple questions exist."""
    for _, _, step in _iter_guide_steps(guide_json):
        raw_sections = step.get("section_to_read")
        sections = [s for s in raw_sections if isinstance(s, str) and s.strip()] if isinstance(raw_sections, list) else []
        step["section_to_read"] = sections

        figure_ids = _normalize_id_list(step.get("relevant_figure_ids"))
        table_ids = _normalize_id_list(step.get("relevant_table_ids"))

        if not figure_ids and sections:
            for section_name in sections:
                figure_ids.extend(section_visual_map.get(section_name, {}).get("figure_ids", []))
            figure_ids = _normalize_id_list(figure_ids)

        if not table_ids and sections:
            for section_name in sections:
                table_ids.extend(section_visual_map.get(section_name, {}).get("table_ids", []))
            table_ids = _normalize_id_list(table_ids)

        step["relevant_figure_ids"] = figure_ids
        step["relevant_table_ids"] = table_ids
        step["needs_figures"] = bool(step.get("needs_figures", False) or figure_ids)
        step["needs_tables"] = bool(step.get("needs_tables", False) or table_ids)

        _ensure_step_questions(step)

    return guide_json


def _check_section_coverage(
    guide_json: dict[str, Any],
    paper_sections: list[dict[str, Any]],
    paper_id: int,
) -> None:
    """Log guide coverage against the paper's extracted section list."""
    guide_sections: set[str] = set()
    for _, _, step in _iter_guide_steps(guide_json):
        raw_sections = step.get("section_to_read") or []
        if not isinstance(raw_sections, list):
            continue
        for section in raw_sections:
            if not isinstance(section, str):
                continue
            normalized = _normalize_section_name(section)
            if normalized:
                guide_sections.add(normalized)

    paper_section_titles = {
        _normalize_section_name(str(section.get("title") or ""))
        for section in paper_sections
        if isinstance(section, dict)
        and section.get("title")
        and not _is_reference_heading(section.get("title"))
    }
    paper_section_titles.discard("")

    uncovered = sorted(paper_section_titles - guide_sections)
    covered_count = len(paper_section_titles) - len(uncovered)
    coverage_pct = (covered_count / max(len(paper_section_titles), 1)) * 100.0

    logger.info(
        "Guide coverage for paper_id=%s: %.0f%% (%d/%d sections)",
        paper_id,
        coverage_pct,
        covered_count,
        len(paper_section_titles),
    )

    if uncovered:
        logger.warning("Guide missing sections for paper_id=%s: %s", paper_id, uncovered)




def _is_intentional_revisit_step(step: dict[str, Any]) -> bool:
    """Return True when step wording explicitly indicates a deliberate revisit."""
    text = " ".join(
        str(step.get(field) or "")
        for field in ("objective", "expected_output")
    ).lower()
    revisit_markers = (
        "revisit",
        "re-read",
        "read again",
        "return to",
        "after reading",
        "cross-check",
        "compare",
        "deepen",
        "synthesize",
    )
    return any(marker in text for marker in revisit_markers)


def _prune_nonessential_section_repetition(guide_json: dict[str, Any]) -> dict[str, Any]:
    """Remove repeated section assignments unless step explicitly requires a revisit."""
    pruned = json.loads(json.dumps(guide_json))
    global_seen: set[str] = set()

    for _, pass_payload in _iter_guide_passes(pruned):
        steps = pass_payload.get("steps") or []
        if not isinstance(steps, list):
            continue

        pass_seen: set[str] = set()
        for step in steps:
            if not isinstance(step, dict):
                continue
            raw_sections = step.get("section_to_read") or []
            if not isinstance(raw_sections, list):
                step["section_to_read"] = []
                continue

            allow_revisit = _is_intentional_revisit_step(step)
            filtered: list[str] = []
            step_seen: set[str] = set()

            for section in raw_sections:
                if not isinstance(section, str):
                    continue
                cleaned = section.strip()
                if not cleaned or _is_reference_heading(cleaned):
                    continue

                norm = _normalize_section_name(cleaned)
                if not norm or norm in step_seen:
                    continue

                if norm in global_seen and not allow_revisit:
                    continue

                filtered.append(cleaned)
                step_seen.add(norm)
                pass_seen.add(norm)
                global_seen.add(norm)

            step["section_to_read"] = filtered

    return pruned


def _validate_section_repetition_policy(guide_json: dict[str, Any]) -> dict[str, Any]:
    """Validate that repeated sections only appear in explicit revisit steps."""
    duplicate_within_pass: set[str] = set()
    duplicate_global_nonrevisit: set[str] = set()
    global_seen: set[str] = set()

    for _, pass_payload in _iter_guide_passes(guide_json):
        pass_seen: set[str] = set()
        steps = pass_payload.get("steps") or []
        if not isinstance(steps, list):
            continue

        for step in steps:
            if not isinstance(step, dict):
                continue

            allow_revisit = _is_intentional_revisit_step(step)
            raw_sections = step.get("section_to_read") or []
            if not isinstance(raw_sections, list):
                continue

            local_seen: set[str] = set()
            for section in raw_sections:
                if not isinstance(section, str):
                    continue
                norm = _normalize_section_name(section.strip())
                if not norm:
                    continue
                if norm in local_seen:
                    continue
                local_seen.add(norm)

                if norm in pass_seen and not allow_revisit:
                    duplicate_within_pass.add(norm)
                if norm in global_seen and not allow_revisit:
                    duplicate_global_nonrevisit.add(norm)

                pass_seen.add(norm)
                global_seen.add(norm)

    return {
        "valid": not duplicate_within_pass and not duplicate_global_nonrevisit,
        "duplicate_within_pass_sections": sorted(duplicate_within_pass),
        "duplicate_global_sections": sorted(duplicate_global_nonrevisit),
    }


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
        max_chars=3500,
    )
    conclusion = _extract_section_text_from_full_text(
        full_text=full_text,
        section_headings=headings,
        keywords=("conclusion", "conclusions", "summary", "future work"),
        max_chars=3000,
    )

    if not introduction:
        introduction = "Not available in extracted full text."
    if not conclusion:
        conclusion = "Not available in extracted full text."

    logger.info(
        "Guide context: intro=%d chars, conclusion=%d chars",
        len(introduction),
        len(conclusion),
    )

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

    def _section_variants(section: str) -> list[str]:
        cleaned = str(section or "").strip()
        if not cleaned:
            return []

        variants = [cleaned]
        lowered = cleaned.lower()

        if lowered.endswith("ies") and len(cleaned) > 4:
            variants.append(cleaned[:-3] + "y")
        elif lowered.endswith("s") and len(cleaned) > 4:
            variants.append(cleaned[:-1])
        elif len(cleaned) > 4:
            variants.append(cleaned + "s")

        return list(dict.fromkeys([item for item in variants if item]))

    expanded_sections: list[str] = []
    for section in step_sections:
        expanded_sections.extend(_section_variants(section))
    expanded_sections = list(dict.fromkeys(expanded_sections))

    lookup = _load_section_lookup(document_id)
    if not lookup:
        return expanded_sections

    resolved: list[str] = []
    for section in expanded_sections:
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
        return expanded_sections

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


def _adaptive_threshold(scores: list[float], base: float = 0.35) -> float:
    if not scores:
        return base
    max_score = max(scores)
    if max_score < 0.30:
        return max_score * 0.8
    return base


def _result_optional_float(value: Any) -> float | None:
    """Best-effort float conversion used by trace preview payloads."""
    try:
        if value is None:
            return None
        return float(value)
    except Exception:  # noqa: BLE001
        return None


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


def _trace_chat_chunk_preview(
    result: Any,
    content_chars: int = _TRACE_CHAT_CHUNK_TEXT_CHARS,
) -> dict[str, Any]:
    """Build a compact preview for one chunk in chat retrieval traces."""
    metadata = _result_metadata(result)
    score_value = _result_score(result)
    retrieval_score = _result_optional_float(metadata.get("retrieval_score"))
    rerank_score = _result_optional_float(metadata.get("rerank_score"))

    if retrieval_score is None:
        retrieval_score = score_value

    content = _result_content(result)
    normalized_content = " ".join(content.split())
    if len(normalized_content) > content_chars:
        normalized_content = normalized_content[:content_chars] + "..."

    preview = {
        "chunk_id": metadata.get("_id") or metadata.get("chunk_id"),
        "score": score_value,
        "retrieval_score": retrieval_score,
        "rerank_score": rerank_score,
        "section_id": metadata.get("section_id"),
        "section_name": metadata.get("section_name") or metadata.get("section_title"),
        "section_title": metadata.get("section_title"),
        "content_type": metadata.get("content_type"),
        "chunk_level": metadata.get("chunk_level"),
        "content_preview": normalized_content,
    }
    # Keep traces concise by dropping optional fields that are missing.
    return {key: value for key, value in preview.items() if value is not None}


def _trace_chat_chunk_previews(
    results: list[Any],
    limit: int = _TRACE_CHAT_CHUNK_PREVIEW_COUNT,
) -> list[dict[str, Any]]:
    """Serialize top chunks for LangSmith visibility in chat flow."""
    return [
        _trace_chat_chunk_preview(result)
        for result in results[: max(0, int(limit))]
    ]


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
    dedup_by_section: bool = True,
) -> list[Any]:
    """
    Deduplicate near-identical chunks using token-overlap Jaccard similarity.
    
    Parameters
    ----------
    chunks : list[Any]
        List of RetrievalResult-like objects to deduplicate.
    similarity_threshold : float
        Jaccard similarity threshold for marking chunks as duplicates (default 0.7).
    dedup_by_section : bool
        When True (default), first removes all but the highest-scoring chunk
        per section_id to prevent parent-child (coarse-fine) redundancy.
    
    Returns
    -------
    list[Any]
        Deduplicated chunk list.
    
    Notes
    -----
    Two-pass deduplication:
    1. Section-based: Keep highest-scoring chunk per section_id
       (prevents coarse + fine chunks from same section appearing together).
    2. Content-based: Jaccard similarity > threshold marks true duplicates.
    """
    
    # First pass: Section-based dedup (prevent hierarchical redundancy)
    if dedup_by_section:
        best_by_section: dict[str, Any] = {}
        for chunk in chunks:
            metadata = _result_metadata(chunk)
            section_id = metadata.get("section_id")
            
            if section_id:
                existing = best_by_section.get(section_id)
                if existing is None or _result_score(chunk) > _result_score(existing):
                    best_by_section[section_id] = chunk
        
        chunks = list(best_by_section.values())
    
    # Second pass: Content-based Jaccard dedup (remove true duplicates)
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


def _filter_unlabeled_sections(chunks: list[Any]) -> list[Any]:
    if not chunks:
        return chunks

    unlabeled_hits = [
        chunk
        for chunk in chunks
        if _result_metadata(chunk).get("section_title") == "Unlabeled Section"
    ]
    if unlabeled_hits and len(unlabeled_hits) <= len(chunks) / 2:
        return [
            chunk
            for chunk in chunks
            if _result_metadata(chunk).get("section_title") != "Unlabeled Section"
        ]
    return chunks


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

    if _ABSTRACT_HEADING not in headings:
        headings = [_ABSTRACT_HEADING, *headings]

    if not headings:
        headings = [_ABSTRACT_HEADING, "Introduction", "Conclusion"]

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

    def _split_sections_for_steps(values: list[str], step_count: int = 9) -> list[list[str]]:
        if not values:
            return [[] for _ in range(step_count)]
        groups: list[list[str]] = [[] for _ in range(step_count)]
        for idx, section in enumerate(values):
            groups[idx % step_count].append(section)
        return groups

    step_sections = _split_sections_for_steps(headings, step_count=9)

    expanded_pairs: list[dict[str, Any]] = []
    while len(expanded_pairs) < 9:
        for pair in question_section_pairs:
            if len(expanded_pairs) >= 9:
                break
            expanded_pairs.append(dict(pair))
    question_section_pairs = expanded_pairs

    for idx, pair in enumerate(question_section_pairs):
        pair["sections"] = step_sections[idx]

    pass1_steps = [
        _mk_step(
            1,
            question_section_pairs[0],
            "Get a fast global understanding of the paper.",
            "A concise summary of the main problem and contribution.",
        ),
        _mk_step(
            2,
            question_section_pairs[1],
            "Map the paper context and terminology.",
            "A high-level map of scope and key concepts.",
        ),
        _mk_step(
            3,
            question_section_pairs[2],
            "Identify headline claims and outcomes.",
            "A short checklist of major claims to verify later.",
        ),
    ]
    pass2_steps = [
        _mk_step(
            1,
            question_section_pairs[3],
            "Understand how the core approach/argument is built.",
            "A clear outline of the method/proof strategy and assumptions.",
        ),
        _mk_step(
            2,
            question_section_pairs[4],
            "Trace implementation or derivation details.",
            "A concrete understanding of intermediate components.",
        ),
        _mk_step(
            3,
            question_section_pairs[5],
            "Connect design choices to reported behavior.",
            "A cause-effect view of why the approach works.",
        ),
    ]
    pass3_steps = [
        _mk_step(
            1,
            question_section_pairs[6],
            "Inspect evidence depth, technical details, and limitations.",
            "A judgment on the strength and boundaries of the claims.",
        ),
        _mk_step(
            2,
            question_section_pairs[7],
            "Stress-test assumptions and generalization.",
            "A list of caveats and transferability risks.",
        ),
        _mk_step(
            3,
            question_section_pairs[8],
            "Extract future work and unresolved questions.",
            "A short list of follow-up research questions.",
        ),
    ]

    guide_json: dict[str, Any] = {
        "paper_title": fallback_title,
        "reading_strategy": {
            "method": "three_pass_method",
            "paper_type": label.lower(),
            "estimated_total_time": "2-3 hours",
        },
        pass1_key: {
            "goal": pass1_goal,
            "estimated_time": "5-10 min",
            "steps": pass1_steps,
        },
        pass2_key: {
            "goal": pass2_goal,
            "estimated_time": "20-40 min",
            "steps": pass2_steps,
        },
        pass3_key: {
            "goal": pass3_goal,
            "estimated_time": "1-2 hrs",
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

@traceable(name="extraction_node", run_type="chain")
def extraction_node(state: dict) -> dict:
    """
    Extract metadata and content from PDF.
    
    Entry point for the workflow when starting from a PDF file.
    """
    import time
    _t = time.perf_counter()
    logger.info("🔍 Extraction node: processing PDF...")
    
    pdf_path = state.get("pdf_path")
    if not pdf_path:
        logger.info(f"Extraction node complete in {time.perf_counter() - _t:.2f}s (error)")
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
        existing_sections = state.get("sections") or []
        section_snippets_by_id: dict[str, str] = {}
        section_snippets_by_title: dict[str, str] = {}
        for section in existing_sections:
            if not isinstance(section, dict):
                continue
            snippet = str(section.get("content_snippet") or "").strip()
            if not snippet:
                continue
            section_id = str(section.get("id") or "").strip()
            if section_id:
                section_snippets_by_id[section_id] = snippet
            section_title = _normalize_section_name(
                str(section.get("title") or section.get("original_name") or "")
            )
            if section_title:
                section_snippets_by_title[section_title] = snippet

        merged_sections: list[dict[str, Any]] = []
        for idx, section in enumerate(metadata.get("sections", []) or [], 1):
            if not isinstance(section, dict):
                continue
            merged_section = dict(section)
            section_id = str(merged_section.get("id") or idx).strip()
            section_title = _normalize_section_name(
                str(merged_section.get("title") or merged_section.get("original_name") or "")
            )
            snippet = section_snippets_by_id.get(section_id) or section_snippets_by_title.get(section_title)
            if snippet:
                merged_section["content_snippet"] = snippet
            merged_sections.append(merged_section)
        logger.info(f"Extraction node complete in {time.perf_counter() - _t:.2f}s")
        return {
            **state,
            "document_id": result["document_id"],
            "full_text": result["full_text"],
            "title": metadata.get("paper_title", ""),
            "abstract": metadata.get("abstract", ""),
                    "sections": merged_sections or metadata.get("sections", []),
            "hierarchy": result["hierarchy"],
            "extraction_files": result.get("files", {}),
            "database": result.get("database", {}),
            "db_paper_id": ((result.get("database") or {}).get("paper_id")),
        }
        
    except Exception as e:
        elapsed = time.perf_counter() - _t
        logger.error(
            f"Extraction node FAILED in {elapsed:.2f}s: {type(e).__name__}: {e}",
            exc_info=True,
        )
        return {**state, "extraction_error": str(e), "extraction_failed": True}


@traceable(name="categorizer_node", run_type="chain")
def categorizer_node(state: dict) -> dict:
    """
    Classify the paper into APPLIED/THEORETICAL/SURVEY via TF-IDF model.
    """
    import time
    _t = time.perf_counter()
    logger.info("📚 Categorizer node: classifying paper...")
    
    title = state.get("title", "").strip()
    abstract = state.get("abstract", "").strip()
    
    if not title and not abstract:
        logger.info(f"Categorizer node complete in {time.perf_counter() - _t:.2f}s (error)")
        return {
            **state,
            "errors": [*state.get("errors", []), "Missing title or abstract for categorization"],
            "confidence": "LOW",
        }
    
    try:
        predictor = _get_tfidf_categorizer()
        prediction = predictor.predict(title=title, abstract=abstract, top_k=3)

        raw_label = str(prediction.get("predicted_label", ""))
        category = _normalize_category_label(raw_label)
        if category is None:
            raise ValueError(f"Model returned unknown category label: {raw_label}")

        top_probs = prediction.get("top_probabilities") or []
        top_probability = 0.0
        if top_probs and isinstance(top_probs[0], dict):
            top_probability = float(top_probs[0].get("probability", 0.0) or 0.0)

        confidence = _confidence_from_probability(top_probability)
        reasoning = (
            f"Predicted using TF-IDF multinomial logistic regression "
            f"(top class probability: {top_probability:.4f})."
        )
        
        logger.info(f"Categorizer node complete in {time.perf_counter() - _t:.2f}s")
        return {
            **state,
            "category": category,
            "confidence": confidence,
            "category_reasoning": reasoning,
        }
        
    except Exception as exc:
        logger.error(f"Categorization failed: {exc}")
        logger.info(f"Categorizer node complete in {time.perf_counter() - _t:.2f}s (error)")
        return {
            **state,
            "errors": [*state.get("errors", []), f"Categorization error: {exc}"],
            "confidence": "LOW",
        }


@traceable(name="_retrieve_for_question", run_type="chain")
def _retrieve_for_question(
    pipeline,
    question: str,
    step_sections: list[str],
    document_id: str,
    pinned_sections: list[str] | None = None,
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
            "trace": {
                "stage": "empty_query",
                "question": question,
                "document_id": document_id,
                "step_sections": step_sections,
            },
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

    _trace_chat_retrieval_stage(
        "scoped_retrieval",
        {
            "question": question,
            "document_id": document_id,
            "expanded_queries": expanded_queries,
            "resolved_sections": resolved_sections,
            "chunk_level": chunk_level,
            "top_k": SCOPED_TOP_K,
            "retrieved_count": len(scoped_hits),
            "chunks": _trace_chat_chunk_previews(scoped_hits),
        },
    )

    merged_hits = _dedupe_results(scoped_hits)

    _trace_chat_retrieval_stage(
        "scoped_dedup",
        {
            "question": question,
            "document_id": document_id,
            "before_count": len(scoped_hits),
            "after_count": len(merged_hits),
            "chunks": _trace_chat_chunk_previews(merged_hits),
        },
    )

    # If scoped pass under-recovers, add a smaller unrestricted pass.
    if len(merged_hits) < 3 and not pinned_sections:
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

        _trace_chat_retrieval_stage(
            "fallback_retrieval",
            {
                "question": question,
                "document_id": document_id,
                "chunk_level": chunk_level,
                "top_k": FALLBACK_TOP_K,
                "retrieved_count": len(fallback_hits),
                "chunks": _trace_chat_chunk_previews(fallback_hits),
            },
        )

        merged_hits = _dedupe_results(merged_hits + fallback_hits)

        _trace_chat_retrieval_stage(
            "fallback_merged_dedup",
            {
                "question": question,
                "document_id": document_id,
                "after_count": len(merged_hits),
                "chunks": _trace_chat_chunk_previews(merged_hits),
            },
        )

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

        if len(compatibility_hits) < 3 and not pinned_sections:
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

        _trace_chat_retrieval_stage(
            "compatibility_retrieval",
            {
                "question": question,
                "document_id": document_id,
                "retrieved_count": len(compatibility_hits),
                "chunks": _trace_chat_chunk_previews(compatibility_hits),
            },
        )

        merged_hits = _dedupe_results(compatibility_hits)

        _trace_chat_retrieval_stage(
            "compatibility_dedup",
            {
                "question": question,
                "document_id": document_id,
                "after_count": len(merged_hits),
                "chunks": _trace_chat_chunk_previews(merged_hits),
            },
        )

    rerank_budget = max(RERANKER_TOP_N, SCOPED_TOP_K + FALLBACK_TOP_K)
    rerank_input = merged_hits[:rerank_budget]

    _trace_chat_retrieval_stage(
        "rerank_input",
        {
            "question": question,
            "document_id": document_id,
            "rerank_budget": rerank_budget,
            "input_count": len(rerank_input),
            "chunks": _trace_chat_chunk_previews(rerank_input),
        },
    )

    reranked_hits = pipeline.rerank_results(
        query=question,
        results=rerank_input,
        top_n=RERANKER_TOP_N,
    )

    reranked_hits = [hit for hit in reranked_hits if not _is_reference_result(hit)]

    _trace_chat_retrieval_stage(
        "rerank_output",
        {
            "question": question,
            "document_id": document_id,
            "top_n": RERANKER_TOP_N,
            "output_count": len(reranked_hits),
            "chunks": _trace_chat_chunk_previews(reranked_hits),
        },
    )

    return reranked_hits, {
        "expanded_queries": expanded_queries,
        "resolved_sections": resolved_sections,
        "chunk_level": chunk_level,
        "trace": {
            "question": question,
            "document_id": document_id,
            "step_sections": step_sections,
            "expanded_queries": expanded_queries,
            "resolved_sections": resolved_sections,
            "chunk_level": chunk_level,
            "scoped_count": len(scoped_hits),
            "merged_count": len(merged_hits),
            "rerank_input_count": len(rerank_input),
            "reranked_count": len(reranked_hits),
        },
    }


@traceable(name="retrieve_and_qa_node", run_type="chain")
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
    defer_answer_generation = bool(state.get("defer_answer_generation", False))

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

        def _process_single_question(idx: int, pair: dict, parent_run_tree=None) -> tuple[int, dict, dict]:
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
                pinned_sections=state.get("pinned_sections"),
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
            rerank_scores = [_result_score(chunk) for chunk in hits]
            threshold = (
                0.0
                if state.get("pinned_sections")
                else _adaptive_threshold(rerank_scores, base=MIN_RELEVANCE_THRESHOLD)
            )
            filtered_hits = [
                chunk for chunk in hits if _result_score(chunk) >= threshold
            ]
            if len(filtered_hits) < 2:
                filtered_hits = hits[:2]

            deduped_hits = _dedupe_near_identical_chunks(filtered_hits)
            deduped_hits = _filter_unlabeled_sections(deduped_hits)
            top_hits = deduped_hits[:QA_TOP_K]

            _trace_chat_retrieval_stage(
                "chat_answer_input",
                {
                    "question": question,
                    "document_id": document_id,
                    "resolved_sections": retrieval_meta.get("resolved_sections", []),
                    "chunk_level": retrieval_meta.get("chunk_level"),
                    "raw_hits_count": len(hits),
                    "threshold": threshold,
                    "threshold_pass_count": len(filtered_hits),
                    "deduped_count": len(deduped_hits),
                    "qa_top_k": QA_TOP_K,
                    "final_input_count": len(top_hits),
                    "chunks": _trace_chat_chunk_previews(top_hits),
                },
            )

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
                    "answer": None if defer_answer_generation else "No relevant content found.",
                    "confidence": None if defer_answer_generation else "LOW",
                    "status": "pending" if defer_answer_generation else "completed",
                }

            context = _build_qa_context(top_hits)
            if not context.strip():
                logger.warning("    No non-reference context for Q%d — using fallback", idx)
                return idx, per_question_result, {
                    "question": question,
                    "answer": None if defer_answer_generation else _build_extractive_fallback_answer(top_hits),
                    "confidence": None if defer_answer_generation else "LOW",
                    "status": "pending" if defer_answer_generation else "completed",
                }

            if defer_answer_generation:
                logger.info("      → Deferred answer generation for Q%d (retrieval payload prepared)", idx)
                return idx, per_question_result, {
                    "question": question,
                    "answer": None,
                    "confidence": None,
                    "status": "pending",
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
                    "status": "completed",
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
                "status": "completed",
            }

        ordered_results: dict[int, tuple[dict, dict]] = {}
        # Capture parent run tree before executor to maintain context across threads
        parent_run_tree = None
        try:
            parent_run_tree = get_current_run_tree()
        except Exception:
            pass  # get_current_run_tree may fail if not in a traced context
        
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_process_single_question, idx, pair, parent_run_tree): idx
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
                        "answer": None if defer_answer_generation else "An error occurred while generating the answer.",
                        "confidence": None if defer_answer_generation else "LOW",
                        "status": "pending" if defer_answer_generation else "failed",
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

        if defer_answer_generation:
            logger.info("Retrieve-and-QA complete: %d question payload(s) prepared for deferred answering", len(qa_results))
        else:
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


@traceable(name="summarizer_node", run_type="chain")
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
    guide_prompt_fn,
) -> dict:
    """
    Generic helper for single-agent guide generation.

    Parameters
    ----------
    state         : current workflow state
    label         : human-readable label for logging (e.g. "APPLIED")
    guide_model_cls : Pydantic model class for final guide output
    guide_prompt_fn : Agent 1 guide prompt function
    """
    logger.info("📖 Guide node [%s]: Agent 1 guide generation…", label)

    title = state.get("title", "")
    abstract = state.get("abstract", "")
    sections = state.get("sections") or []
    full_text = state.get("full_text", "")
    document_id = state.get("document_id", "")
    paper_id = int(state.get("db_paper_id") or state.get("paper_id") or 0)

    if not title or not abstract:
        return {
            **state,
            "errors": [*state.get("errors", []), f"Missing title or abstract for {label} guide"],
        }

    try:
        num_figures = sum(s.get("stats", {}).get("figures", 0) for s in sections)
        num_tables = sum(s.get("stats", {}).get("tables", 0) for s in sections)
        visual_context = _extract_visual_context(document_id=document_id, sections=sections)
        has_snippets = sum(1 for section in sections if isinstance(section, dict) and section.get("content_snippet"))
        logger.info(
            "Guide input: %d sections, %d with content snippets",
            len(sections),
            has_snippets,
        )

        # Agent 1 guide: structured full guide generation (includes questions).
        planner_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1)
        structured_planner_llm = planner_llm.with_structured_output(guide_model_cls)

        planner_prompt_kwargs = {
            "title": title,
            "abstract": abstract,
            "sections": sections,
            "num_figures": num_figures,
            "num_tables": num_tables,
        }

        prompt_parameters = inspect.signature(guide_prompt_fn).parameters
        if "introduction" in prompt_parameters or "conclusion" in prompt_parameters:
            introduction, conclusion = _extract_intro_conclusion_context(
                full_text=full_text,
                sections=sections,
            )
            if "introduction" in prompt_parameters:
                planner_prompt_kwargs["introduction"] = introduction
            if "conclusion" in prompt_parameters:
                planner_prompt_kwargs["conclusion"] = conclusion

        planner_prompt = guide_prompt_fn(**planner_prompt_kwargs)

        planner_json: dict[str, Any] | None = None
        validation_report: dict[str, Any] | None = None
        attempt_prompt = planner_prompt

        for attempt in range(1, _GUIDE_VALIDATION_ATTEMPTS + 1):
            planner_model = structured_planner_llm.invoke(attempt_prompt)
            planner_json = planner_model.model_dump()
            planner_json = _normalize_guide_steps(
                guide_json=planner_json,
                section_visual_map=visual_context["section_visual_map"],
            )
            planner_json = _prune_nonessential_section_repetition(planner_json)
            validation_report = _validate_section_repetition_policy(planner_json)

            if validation_report["valid"]:
                break

            logger.warning(
                "Agent 1 planner [%s] repetition validation failed (attempt %d/%d): "
                "duplicates_within_pass=%d, duplicates_global=%d",
                label,
                attempt,
                _GUIDE_VALIDATION_ATTEMPTS,
                len(validation_report["duplicate_within_pass_sections"]),
                len(validation_report["duplicate_global_sections"]),
            )

            if attempt < _GUIDE_VALIDATION_ATTEMPTS:
                attempt_prompt = (
                    f"{planner_prompt}\n\n"
                    "VALIDATION FEEDBACK FROM PREVIOUS DRAFT:\n"
                    f"- Duplicate sections within same pass: {json.dumps(validation_report['duplicate_within_pass_sections'], ensure_ascii=False)}\n"
                    f"- Duplicate sections across passes (without explicit revisit intent): {json.dumps(validation_report['duplicate_global_sections'], ensure_ascii=False)}\n"
                    "Return a corrected guide JSON that follows the three-pass method, avoids unnecessary repetition, and keeps questions_to_answer short and simple."
                )

        if planner_json is None:
            raise ValueError("Guide planner returned no output")

        if validation_report is None or not validation_report["valid"]:
            logger.warning(
                "Agent 1 planner [%s] still had unnecessary repeats after retries; applying deterministic pruning",
                label,
            )
            planner_json = _prune_nonessential_section_repetition(planner_json)
            planner_json = _normalize_guide_steps(
                guide_json=planner_json,
                section_visual_map=visual_context["section_visual_map"],
            )

        _check_section_coverage(planner_json, sections, paper_id)

        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        guide_plan_path = output_dir / f"{document_id}_guide_plan.json"
        with open(guide_plan_path, "w", encoding="utf-8") as f:
            json.dump(planner_json, f, indent=2, ensure_ascii=False)
        logger.info("✅ Reading guide plan saved to: %s", guide_plan_path)

        guide_json = planner_json

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
        guide_path = output_dir / f"{document_id}_guide.json"
        with open(guide_path, "w", encoding="utf-8") as f:
            json.dump(guide_json, f, indent=2, ensure_ascii=False)
        logger.info("✅ Reading guide saved to: %s", guide_path)

        return {
            **state,
            "reading_guide_plan": planner_json,
            "guide_plan_file_path": str(guide_plan_path),
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
            guide_plan_path = output_dir / f"{document_id}_guide_plan.json"
            with open(guide_plan_path, "w", encoding="utf-8") as f:
                json.dump(guide_json, f, indent=2, ensure_ascii=False)

            guide_path = output_dir / f"{document_id}_guide.json"
            with open(guide_path, "w", encoding="utf-8") as f:
                json.dump(guide_json, f, indent=2, ensure_ascii=False)

            return {
                **state,
                "reading_guide_plan": guide_json,
                "guide_plan_file_path": str(guide_plan_path),
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


@traceable(name="applied_guide_node", run_type="chain")
def applied_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for APPLIED papers."""
    return _run_guide_node(
        state,
        label="APPLIED",
        guide_model_cls=AppliedReadingGuide,
        guide_prompt_fn=applied_guide_prompt,
    )


@traceable(name="theoretical_guide_node", run_type="chain")
def theoretical_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for THEORETICAL papers."""
    return _run_guide_node(
        state,
        label="THEORETICAL",
        guide_model_cls=TheoreticalReadingGuide,
        guide_prompt_fn=theoretical_guide_prompt,
    )


@traceable(name="survey_guide_node", run_type="chain")
def survey_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for SURVEY papers."""
    return _run_guide_node(
        state,
        label="SURVEY",
        guide_model_cls=SurveyReadingGuide,
        guide_prompt_fn=survey_guide_prompt,
    )



# ---------------------------------------------------------------------------
# Data Processing Pipeline Nodes
# ---------------------------------------------------------------------------
# These nodes wrap the extraction and indexing pipelines into LangGraph nodes
# for unified workflow visibility and control.

def ingest_node(state: dict) -> dict:
    """
    Ingest and validate PDF; run OCR if needed.
    
    Inputs:
        pdf_path (str): path to PDF file
        force_ocr (bool): whether to force OCR reprocessing
    
    Outputs:
        document_id (str): assigned document ID
        validated_document (ValidatedDocument): validated PDF structure
        ingest_status (dict): metadata about ingestion (page_count, ocr_applied)
    """
    logger.info("📥 Ingest node: validating PDF...")
    
    pdf_path = state.get("pdf_path")
    if not pdf_path:
        return {
            **state,
            "ingest_status": {"error": "No pdf_path provided"},
        }
    
    try:
        from extraction.pipelines.ingest_pipeline import IngestPipeline
        
        pipeline = IngestPipeline()
        result = pipeline.process(
            pdf_path=Path(pdf_path),
            force_ocr=state.get("force_ocr", False),
        )
        
        logger.info("✅ Ingest node completed: %d pages, document_id=%s", result.page_count, result.document_id)
        
        return {
            **state,
            "document_id": result.document_id,
            "validated_document": result,
            "ingest_status": {
                "page_count": result.page_count,
                "ocr_applied": result.was_reprocessed,
            },
        }
    except Exception as exc:
        logger.error("Ingest node failed: %s", exc, exc_info=True)
        return {
            **state,
            "ingest_status": {"error": str(exc)},
            "errors": [*state.get("errors", []), f"Ingest error: {exc}"],
        }


def metadata_extraction_node(state: dict) -> dict:
    """
    Extract metadata (title, abstract, sections) using Groq LLM.
    
    Inputs:
        validated_document (ValidatedDocument): from ingest_node
        document_id (str): from ingest_node
    
    Outputs:
        metadata (dict): extracted title, abstract, keywords, sections
        metadata_status (dict): processing stats (processing_time, fields_found)
    """
    logger.info("🏷️ Metadata extraction node: extracting title/abstract/sections...")
    
    validated_doc = state.get("validated_document")
    document_id = state.get("document_id")
    
    if not validated_doc or not document_id:
        return {
            **state,
            "metadata_status": {"error": "Missing validated_document or document_id"},
        }
    
    try:
        from extraction.pipelines.metadata_pipeline import MetadataExtractionPipeline
        import time
        
        pipeline = MetadataExtractionPipeline()
        start_time = time.time()
        result = pipeline.process(validated_document=validated_doc)
        elapsed = time.time() - start_time
        
        fields_extracted = []
        if result.title:
            fields_extracted.append("title")
        if result.abstract:
            fields_extracted.append("abstract")
        if result.keywords:
            fields_extracted.append("keywords")
        if result.sections:
            fields_extracted.append("sections")
        
        logger.info("✅ Metadata extraction completed in %.2fs: %s", elapsed, ", ".join(fields_extracted))
        
        return {
            **state,
            "metadata": {
                "title": result.title,
                "abstract": result.abstract,
                "keywords": result.keywords or [],
                "sections": result.sections or [],
            },
            "metadata_status": {
                "processing_time_sec": elapsed,
                "fields_found": fields_extracted,
            },
        }
    except Exception as exc:
        logger.error("Metadata extraction failed: %s", exc, exc_info=True)
        return {
            **state,
            "metadata_status": {"error": str(exc)},
            "errors": [*state.get("errors", []), f"Metadata extraction error: {exc}"],
        }


def section_hierarchy_node(state: dict) -> dict:
    """
    Build hierarchical section tree from extracted metadata.
    
    Inputs:
        validated_document (ValidatedDocument)
        metadata (dict): from metadata_extraction_node
        document_id (str)
    
    Outputs:
        section_hierarchy (dict): nested section tree
        hierarchy_status (dict): stats (depth, root_sections)
    """
    logger.info("🌳 Section hierarchy node: building section tree...")
    
    validated_doc = state.get("validated_document")
    metadata = state.get("metadata", {})
    document_id = state.get("document_id")
    
    if not all([validated_doc, document_id]):
        return {
            **state,
            "hierarchy_status": {"error": "Missing validated_document or document_id"},
        }
    
    try:
        from extraction.pipelines.section_hierarchy_pipeline import SectionHierarchyPipeline
        
        pipeline = SectionHierarchyPipeline()
        hierarchy = pipeline.process(validated_document=validated_doc)
        
        # Compute stats
        depth = _compute_hierarchy_depth(hierarchy)
        root_count = len(hierarchy.get("children", []))
        
        logger.info("✅ Section hierarchy built: depth=%d, root_sections=%d", depth, root_count)
        
        return {
            **state,
            "section_hierarchy": hierarchy,
            "hierarchy_status": {
                "depth": depth,
                "root_sections": root_count,
            },
        }
    except Exception as exc:
        logger.error("Section hierarchy building failed: %s", exc, exc_info=True)
        return {
            **state,
            "hierarchy_status": {"error": str(exc)},
            "errors": [*state.get("errors", []), f"Hierarchy error: {exc}"],
        }


def db_ingestion_node(state: dict) -> dict:
    """
    Persist extracted data to PostgreSQL.
    
    Inputs:
        document_id (str)
        validated_document (ValidatedDocument)
        metadata (dict)
        section_hierarchy (dict)
    
    Outputs:
        db_paper_id (int): assigned database paper ID
        db_status (dict): ingestion metadata (stored flag, timestamps)
    """
    logger.info("💾 DB ingestion node: persisting to PostgreSQL...")
    
    pdf_path = state.get("pdf_path")
    document_id = state.get("document_id")
    validated_doc = state.get("validated_document")
    metadata = state.get("metadata", {})
    hierarchy = state.get("section_hierarchy", {})
    
    if not all([document_id, validated_doc]):
        return {
            **state,
            "db_status": {"error": "Missing document_id or validated_document"},
        }
    
    try:
        from extraction.pipelines.db_ingestion_pipeline import DBIngestionPipeline
        
        pipeline = DBIngestionPipeline()
        result = pipeline.ingest(
            pdf_path=Path(pdf_path) if pdf_path else None,
            document_id=document_id,
            validated_document=validated_doc,
        )
        
        logger.info("✅ DB ingestion completed: paper_id=%d", result.paper_id)
        
        return {
            **state,
            "db_paper_id": result.paper_id,
            "db_status": {
                "stored": True,
                "paper_id": result.paper_id,
            },
        }
    except Exception as exc:
        logger.error("DB ingestion failed: %s", exc, exc_info=True)
        return {
            **state,
            "db_status": {"error": str(exc), "stored": False},
            "errors": [*state.get("errors", []), f"DB ingestion error: {exc}"],
        }


def chunking_node(state: dict) -> dict:
    """
    Chunk extracted sections into token-aware chunks with section context.
    
    Inputs:
        metadata (dict): contains sections
        document_id (str)
    
    Outputs:
        chunks (list[Chunk]): section-aware chunks ready for embedding
        chunking_status (dict): stats (num_chunks, avg_chunk_tokens)
    """
    logger.info("✂️ Chunking node: splitting sections into chunks...")
    
    metadata = state.get("metadata", {})
    document_id = state.get("document_id")
    
    if not metadata or not document_id:
        return {
            **state,
            "chunking_status": {"error": "Missing metadata or document_id"},
        }
    
    try:
        from rag.retrieval.chunking.section_chunker import chunk_paper
        from rag.retrieval.config import COARSE_CHUNK_SIZE, COARSE_CHUNK_OVERLAP, DENSE_MODEL
        
        sections = metadata.get("sections", [])
        if not sections:
            logger.warning("No sections to chunk for document %s", document_id)
            return {
                **state,
                "chunks": [],
                "chunking_status": {"num_chunks": 0},
            }
        
        chunks = chunk_paper(
            sections=sections,
            paper_id=document_id,
            chunk_size=COARSE_CHUNK_SIZE,
            overlap=COARSE_CHUNK_OVERLAP,
            model_name=DENSE_MODEL,
        )
        
        avg_tokens = (
            sum(c.token_count for c in chunks) / len(chunks)
            if chunks
            else 0
        )
        
        logger.info("✅ Chunking completed: %d chunks, avg %.1f tokens", len(chunks), avg_tokens)
        
        return {
            **state,
            "chunks": chunks,
            "chunking_status": {
                "num_chunks": len(chunks),
                "avg_chunk_tokens": avg_tokens,
            },
        }
    except Exception as exc:
        logger.error("Chunking failed: %s", exc, exc_info=True)
        return {
            **state,
            "chunking_status": {"error": str(exc)},
            "errors": [*state.get("errors", []), f"Chunking error: {exc}"],
        }


def indexing_node(state: dict) -> dict:
    """
    Embed chunks (dense + sparse) and upsert to Qdrant vector store.
    
    Inputs:
        chunks (list[Chunk]): from chunking_node
        document_id (str)
        pdf_path (str): for hierarchy resolution
    
    Outputs:
        indexed_chunks_count (int): number of chunks successfully indexed
        indexing_status (dict): stats (embedding_time, upsert_time)
    """
    import time
    _t = time.perf_counter()
    logger.info("🔍 Indexing node: embedding and upserting to Qdrant...")
    
    chunks = state.get("chunks", [])
    document_id = state.get("document_id") or state.get("metadata", {}).get("document_id")
    pdf_path = state.get("pdf_path")
    
    # Check if we have chunks and document_id before proceeding
    if not chunks or not document_id:
        logger.warning(
            f"Indexing node: no chunks ({len(chunks)}) or document_id ({document_id}) "
            f"in state — skipping to avoid re-chunking from disk"
        )
        logger.info(f"Indexing node complete in {time.perf_counter() - _t:.2f}s (skipped)")
        return {**state, "indexing_skipped": True, "indexing_reason": "empty_chunks_or_id"}
    
    logger.info(f"Indexing node: received {len(chunks)} chunks for document {document_id}")
    
    try:
        from pathlib import Path
        import time
        
        pipeline = _get_retrieval_pipeline()
        
        # Build hierarchy path for indexing
        hierarchy_path = Path("output") / f"{document_id}_hierarchy.json"
        if not hierarchy_path.exists():
            logger.warning("Hierarchy file not found at %s; attempting indexing anyway", hierarchy_path)
        
        pdf_path_obj = None
        if pdf_path and Path(pdf_path).exists():
            pdf_path_obj = Path(pdf_path)
        
        start_time = time.time()
        result = pipeline.index(
            hierarchy_json_path=hierarchy_path,
            output_dir=Path("output"),
            pdf_path=pdf_path_obj,
        )
        elapsed = time.time() - start_time
        
        logger.info("✅ Indexing completed in %.2fs: %d total chunks indexed", elapsed, result.total_chunks)
        logger.info(f"Indexing node complete in {time.perf_counter() - _t:.2f}s")
        
        return {
            **state,
            "indexed_chunks_count": result.total_chunks,
            "indexing_status": {
                "embedding_time_sec": elapsed,
                "chunks_indexed": result.total_chunks,
            },
        }
    except Exception as exc:
        logger.error("Indexing failed: %s", exc, exc_info=True)
        logger.info(f"Indexing node complete in {time.perf_counter() - _t:.2f}s (error)")
        return {
            **state,
            "indexing_status": {"error": str(exc)},
            "errors": [*state.get("errors", []), f"Indexing error: {exc}"],
        }


def _compute_hierarchy_depth(node: dict, current_depth: int = 0) -> int:
    """Recursively compute max depth of hierarchy tree."""
    children = node.get("children", [])
    if not children:
        return current_depth
    return max(_compute_hierarchy_depth(child, current_depth + 1) for child in children)


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


def route_after_guide(state: dict) -> str:
    """Route guide path: to retrieval/qa, direct to chunking, or end."""
    skip_qa = bool(state.get("skip_retrieve_and_qa", False))
    skip_all = bool(state.get("guide_only_no_further_processing", False))
    
    if skip_all:
        logger.info("→ Guide-only mode (terminal): skipping all downstream processing")
        return "end"
    elif skip_qa:
        logger.info("→ Guide-only mode: skipping retrieve_and_qa → going to chunking")
        return "chunking"
    
    return "retrieve_and_qa"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph():
    """
    Build and compile the LangGraph pipeline with all processing stages.

    Complete Workflow:
    ------------------
    Ingestion & Extraction Phase:
        START → ingest → metadata_extraction → section_hierarchy → db_ingestion
    
    Classification & Analysis Phase:
        → extraction_mapping → categorizer → <category_guide> → retrieve_and_qa
    
    Indexing Phase:
        → chunking → indexing → END

    Alternative paths:
        - If query provided: skip guide, go directly to retrieve_and_qa
        - If category unknown: route to summarizer instead of guide
        - Chunking/indexing can run in parallel with QA or sequentially

    Returns:
        A compiled LangGraph CompiledGraph ready for invocation.
    """
    builder = StateGraph(dict)

    # ── Data Pipeline Nodes (Ingestion & Extraction) ─────────────────────────
    builder.add_node("ingest", ingest_node)
    builder.add_node("metadata_extraction", metadata_extraction_node)
    builder.add_node("section_hierarchy", section_hierarchy_node)
    builder.add_node("db_ingestion", db_ingestion_node)

    # ── Analysis Pipeline Nodes ────────────────────────────────────────────────
    builder.add_node("extraction_mapping", extraction_node)  # Maps extraction results to expected state keys
    builder.add_node("categorizer", categorizer_node)

    # Three category-specific guide nodes
    builder.add_node("applied_guide", applied_guide_node)
    builder.add_node("theoretical_guide", theoretical_guide_node)
    builder.add_node("survey_guide", survey_guide_node)

    # ── Retrieval & QA Nodes ───────────────────────────────────────────────────
    builder.add_node("retrieve_and_qa", retrieve_and_qa_node)
    builder.add_node("summarizer", summarizer_node)

    # ── Indexing & Vector Storage Nodes ────────────────────────────────────────
    builder.add_node("chunking", chunking_node)
    builder.add_node("indexing", indexing_node)

    # ── Edges: Ingestion Pipeline Chain ────────────────────────────────────────
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "metadata_extraction")
    builder.add_edge("metadata_extraction", "section_hierarchy")
    builder.add_edge("section_hierarchy", "db_ingestion")
    builder.add_edge("db_ingestion", "extraction_mapping")

    # ── Edges: Classification Pipeline ─────────────────────────────────────────
    builder.add_edge("extraction_mapping", "categorizer")

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

    # ── Edges: Guide Nodes → Retrieval ─────────────────────────────────────────
    # Guide nodes can continue into retrieve-and-QA or terminate in guide-only mode.
    for guide_node in _CATEGORY_GUIDE_NODE.values():
        builder.add_conditional_edges(
            guide_node,
            route_after_guide,
            {
                "retrieve_and_qa": "retrieve_and_qa",
                "chunking": "chunking",  # Allow guide to skip QA and go straight to chunking
                "end": END,
            },
        )

    # ── Edges: Retrieval & Summarization ───────────────────────────────────────
    # Both retrieve_and_qa and summarizer flow to chunking for index building
    builder.add_edge("retrieve_and_qa", "chunking")
    builder.add_edge("summarizer", "chunking")

    # ── Edges: Indexing Pipeline Chain ─────────────────────────────────────────
    builder.add_edge("chunking", "indexing")
    builder.add_edge("indexing", END)

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
