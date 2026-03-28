"""Technical-term extraction service for API bundle payloads."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .definition_lookup import DefinitionLookup
from .detector import TechnicalTermDetector


logger = logging.getLogger(__name__)

_DETECTOR: Optional[TechnicalTermDetector] = None
_DEFINITION_LOOKUP: Optional[DefinitionLookup] = None
_LLM_OVERRIDES: Dict[tuple[int, str], Dict[str, Any]] = {}


def _get_detector() -> TechnicalTermDetector:
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = TechnicalTermDetector()
    return _DETECTOR


def _get_definition_lookup() -> DefinitionLookup:
    global _DEFINITION_LOOKUP
    if _DEFINITION_LOOKUP is None:
        _DEFINITION_LOOKUP = DefinitionLookup()
    return _DEFINITION_LOOKUP


def _normalize_title(title: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (title or "").strip().lower())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _is_abstract_title(title: str) -> bool:
    normalized = _normalize_title(title)
    return bool(re.search(r"\babstract\b", normalized))


def _is_introduction_title(title: str) -> bool:
    normalized = _normalize_title(title)
    return bool(re.search(r"\bintro(?:duction)?\b", normalized))


def _collect_focus_blocks(paper: Dict[str, Any], sections: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    blocks: List[Dict[str, str]] = []

    paper_abstract = str(paper.get("abstract") or "").strip()
    if paper_abstract:
        blocks.append({"scope": "abstract", "text": paper_abstract})

    for section in sections:
        title = str(section.get("title") or "")
        content = str(section.get("content") or "").strip()
        if not content:
            continue

        if _is_abstract_title(title):
            blocks.append({"scope": "abstract", "text": content})
            continue

        if _is_introduction_title(title):
            blocks.append({"scope": "introduction", "text": content})

    deduped: List[Dict[str, str]] = []
    seen = set()
    for block in blocks:
        key = (block["scope"], block["text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(block)

    return deduped


def get_term_context_text(
    paper: Dict[str, Any],
    sections: List[Dict[str, Any]],
    term: str,
) -> str:
    """Return a concise context sentence from abstract/introduction blocks."""
    blocks = _collect_focus_blocks(paper, sections)
    if not blocks:
        return ""

    term_lower = term.lower().strip()
    if not term_lower:
        return ""

    for block in blocks:
        sentences = re.split(r"(?<=[.!?])\s+", block["text"])
        for sentence in sentences:
            if term_lower in sentence.lower():
                return sentence.strip()

    return blocks[0]["text"][:400].strip()


def set_llm_definition_override(paper_id: int, term: str, definition: str) -> Dict[str, Any]:
    """Persist in-memory LLM definition override for a paper/term pair."""
    key = (int(paper_id), term.strip().lower())
    record = {
        "definition": definition.strip(),
        "definition_source": "llm",
        "definition_status": "ready",
    }
    _LLM_OVERRIDES[key] = record
    return record


def extract_technical_terms_for_bundle(
    paper: Dict[str, Any],
    sections: List[Dict[str, Any]],
    *,
    min_score: float = 0.65,
    max_terms: int = 12,
) -> List[Dict[str, Any]]:
    """Extract technical terms from abstract and introduction text only."""
    blocks = _collect_focus_blocks(paper, sections)
    if not blocks:
        return []

    try:
        detector = _get_detector()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Technical term detector initialization failed: %s", exc)
        return []

    definition_lookup = _get_definition_lookup()

    merged: Dict[str, Dict[str, Any]] = {}
    for block in blocks:
        try:
            detected = detector.detect(block["text"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Technical term detection failed for %s: %s", block["scope"], exc)
            continue

        for item in detected:
            score = float(item.get("score") or 0.0)
            if score < min_score:
                continue

            term = str(item.get("term") or "").strip()
            if not term:
                continue
            key = term.lower()

            existing = merged.get(key)
            if existing is None or score > float(existing.get("score") or 0.0):
                definition, source = definition_lookup.lookup_api_definition(term)
                merged[key] = {
                    "term": term,
                    "type": item.get("type"),
                    "score": round(score, 2),
                    "expansion": item.get("expansion"),
                    "source_sections": [block["scope"]],
                    "definition": definition,
                    "definition_source": source,
                    "definition_status": "ready" if definition else "pending_llm",
                }
            else:
                scopes = set(existing.get("source_sections") or [])
                scopes.add(block["scope"])
                existing["source_sections"] = sorted(scopes)

    terms = list(merged.values())

    # Apply on-demand LLM overrides (from generate/regenerate button actions).
    for item in terms:
        key = (int(paper.get("id") or 0), str(item.get("term") or "").lower())
        override = _LLM_OVERRIDES.get(key)
        if override:
            item["definition"] = override["definition"]
            item["definition_source"] = override["definition_source"]
            item["definition_status"] = override["definition_status"]

    priority = {
        "dbpedia": 0,
        "dictionary": 1,
        "wikipedia": 2,
        "llm": 3,
        None: 4,
    }
    terms.sort(
        key=lambda item: (
            priority.get(item.get("definition_source"), 2),
            -float(item.get("score") or 0.0),
            str(item.get("term") or ""),
        )
    )
    return terms[:max_terms]
