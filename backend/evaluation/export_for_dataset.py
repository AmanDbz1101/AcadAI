"""Export guide-step section context for external annotation workflows."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag.retrieval import RetrievalPipeline  # type: ignore[import-not-found]
from evaluation.config import PAPERS  # type: ignore[import-not-found]


EXPORT_PATH = PROJECT_ROOT / "evaluation/dataset/export_for_annotation.json"


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _guide_path_candidates(document_id: str) -> list[Path]:
    return [
        PROJECT_ROOT / "output" / f"{document_id}_guide.json",
        PROJECT_ROOT.parent / "output" / f"{document_id}_guide.json",
    ]


def _hierarchy_path_candidates(document_id: str) -> list[Path]:
    return [
        PROJECT_ROOT / "output" / f"{document_id}_hierarchy.json",
        PROJECT_ROOT.parent / "output" / f"{document_id}_hierarchy.json",
    ]


def _find_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _extract_all_sections(hierarchy_json: dict[str, Any]) -> list[dict[str, Any]]:
    hierarchy = hierarchy_json.get("hierarchy", hierarchy_json)
    sections = hierarchy.get("sections", [])
    return sections if isinstance(sections, list) else []


def _build_section_maps(sections: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Return maps for normalized title/full-label/numbering to section_id."""
    by_title: dict[str, str] = {}
    by_full_label: dict[str, str] = {}
    by_numbering: dict[str, str] = {}

    for section in sections:
        sid = str(section.get("section_id") or "").strip()
        if not sid:
            continue
        title = str(section.get("title") or "").strip()
        numbering = str(section.get("numbering") or "").strip()

        if title:
            by_title[_normalize(title)] = sid

        if numbering:
            by_numbering[_normalize(numbering)] = sid
            if title:
                full_label = _normalize(f"{numbering} {title}")
                by_full_label[full_label] = sid

    return by_title, by_full_label, by_numbering


def _resolve_section_id(
    section_label: str,
    by_title: dict[str, str],
    by_full_label: dict[str, str],
    by_numbering: dict[str, str],
) -> str | None:
    normalized = _normalize(section_label)
    if not normalized:
        return None

    if normalized in by_full_label:
        return by_full_label[normalized]
    if normalized in by_title:
        return by_title[normalized]
    if normalized in by_numbering:
        return by_numbering[normalized]

    number_match = re.match(r"^(\d+(?:\.\d+)*)", normalized)
    if number_match:
        numeric_prefix = _normalize(number_match.group(1))
        if numeric_prefix in by_numbering:
            return by_numbering[numeric_prefix]

    for title_key, section_id in by_title.items():
        if normalized in title_key or title_key in normalized:
            return section_id

    return None


def _extract_guide_steps(guide_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract all guide steps with section labels from any pass structure."""
    steps_out: list[dict[str, Any]] = []

    for _, maybe_pass in guide_json.items():
        if not isinstance(maybe_pass, dict):
            continue
        maybe_steps = maybe_pass.get("steps")
        if not isinstance(maybe_steps, list):
            continue

        for step in maybe_steps:
            if not isinstance(step, dict):
                continue
            step_number = step.get("step_number")
            objective = str(step.get("objective") or "").strip()
            expected_output = str(step.get("expected_output") or "").strip()

            if objective:
                step_title = f"Step {step_number}: {objective}" if step_number is not None else objective
            else:
                step_title = f"Step {step_number}" if step_number is not None else "Step"

            step_description = objective or expected_output
            section_labels = step.get("section_to_read") or []
            if not isinstance(section_labels, list):
                section_labels = []

            steps_out.append(
                {
                    "guide_step_title": step_title,
                    "guide_step_description": step_description,
                    "section_labels": [str(s) for s in section_labels if str(s).strip()],
                }
            )

    return steps_out


def export_for_dataset() -> None:
    pipeline = RetrievalPipeline()
    export_rows: list[dict[str, Any]] = []
    per_paper_counts: dict[str, int] = {}

    for paper in PAPERS:
        paper_id = str(paper.get("paper_id") or "")
        paper_type = str(paper.get("paper_type") or "")
        document_id = str(paper.get("document_id") or "").strip()

        if not document_id:
            print(f"Skipping {paper_id}: document_id is empty in evaluation/config.py")
            per_paper_counts[paper_id] = 0
            continue

        guide_path = _find_existing(_guide_path_candidates(document_id))
        hierarchy_path = _find_existing(_hierarchy_path_candidates(document_id))

        if guide_path is None:
            print(f"Skipping {paper_id}: guide file not found for document_id={document_id}")
            per_paper_counts[paper_id] = 0
            continue

        if hierarchy_path is None:
            print(f"Skipping {paper_id}: hierarchy file not found for document_id={document_id}")
            per_paper_counts[paper_id] = 0
            continue

        guide_json = _load_json(guide_path)
        hierarchy_json = _load_json(hierarchy_path)
        if not isinstance(guide_json, dict) or not isinstance(hierarchy_json, dict):
            print(f"Skipping {paper_id}: invalid guide/hierarchy json format")
            per_paper_counts[paper_id] = 0
            continue

        steps = _extract_guide_steps(guide_json)
        all_sections = _extract_all_sections(hierarchy_json)
        by_title, by_full_label, by_numbering = _build_section_maps(all_sections)
        title_by_id = {
            str(s.get("section_id")): str(s.get("title") or "")
            for s in all_sections
            if s.get("section_id")
        }

        exported_count = 0
        for step in steps:
            guide_step_title = str(step.get("guide_step_title") or "").strip()
            guide_step_description = str(step.get("guide_step_description") or "").strip()
            section_labels = step.get("section_labels") or []

            for section_label in section_labels:
                section_id = _resolve_section_id(
                    section_label=str(section_label),
                    by_title=by_title,
                    by_full_label=by_full_label,
                    by_numbering=by_numbering,
                )
                if not section_id:
                    continue

                chunks = pipeline.retrieve_with_section_scope(
                    query=guide_step_title,
                    section_id=section_id,
                    document_id=document_id,
                    top_k=10,
                    rerank=True,
                )

                section_context = "\n\n".join(
                    str(getattr(chunk, "content", "") or "").strip()
                    for chunk in chunks
                    if str(getattr(chunk, "content", "") or "").strip()
                )

                chunk_ids: list[str] = []
                for chunk in chunks:
                    metadata = getattr(chunk, "metadata", {})
                    if not isinstance(metadata, dict):
                        continue
                    cid = str(metadata.get("chunk_id") or "").strip()
                    if cid:
                        chunk_ids.append(cid)

                export_rows.append(
                    {
                        "paper_id": paper_id,
                        "paper_type": paper_type,
                        "document_id": document_id,
                        "section_id": section_id,
                        "section_title": title_by_id.get(section_id) or str(section_label),
                        "guide_step_title": guide_step_title,
                        "guide_step_description": guide_step_description,
                        "section_context": section_context,
                        "chunk_ids": chunk_ids,
                    }
                )
                exported_count += 1

        per_paper_counts[paper_id] = exported_count

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EXPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(export_rows, f, indent=2, ensure_ascii=False)

    print("\nExport summary:")
    for paper_id, count in per_paper_counts.items():
        print(f"  {paper_id}: {count} sections exported")
    print(f"\nSaved: {EXPORT_PATH}")


def main() -> None:
    export_for_dataset()


if __name__ == "__main__":
    main()
