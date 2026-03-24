"""Export guide-step section context for external annotation workflows."""

from __future__ import annotations

import json
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


def _resolve_section_from_results(
    pipeline: RetrievalPipeline,
    query_results: list,
    section_label: str,
) -> tuple[str | None, str]:
    """Resolve (section_id, section_title) from retrieval results.

    Primary path reads metadata directly from query hits.
    Fallback path uses hit `_id` to retrieve full payload from Qdrant.
    """
    section_title = section_label

    for result in query_results:
        metadata = getattr(result, "metadata", {})
        if not isinstance(metadata, dict):
            continue

        direct_section_id = str(metadata.get("section_id") or "").strip()
        if direct_section_id:
            direct_section_title = str(metadata.get("section_title") or section_label).strip() or section_label
            return direct_section_id, direct_section_title

        point_id = metadata.get("_id")
        if not point_id:
            continue

        try:
            store_manager = pipeline._get_store_manager()  # noqa: SLF001
            collection_name = store_manager.collection_name
            retrieved = store_manager.client.retrieve(
                collection_name=collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            continue

        if not retrieved:
            continue

        payload = getattr(retrieved[0], "payload", {})
        if not isinstance(payload, dict):
            continue

        payload_section_id = str(payload.get("section_id") or "").strip()
        if not payload_section_id:
            continue

        payload_section_title = str(payload.get("section_title") or section_label).strip() or section_label
        return payload_section_id, payload_section_title

    return None, section_title


def _content_type_filter_supported(pipeline: RetrievalPipeline) -> bool:
    """Return True when Qdrant has a payload index for `content_type`."""
    try:
        store_manager = pipeline._get_store_manager()  # noqa: SLF001
        info = store_manager.client.get_collection(store_manager.collection_name)
        payload_schema = getattr(info, "payload_schema", None)
        if isinstance(payload_schema, dict):
            return "content_type" in payload_schema
    except Exception:
        return False
    return False


def load_guide(document_id: str) -> list:
    # Guide files are saved at:
    # /home/aman/storage/Python/Projects/Research Paper Assistant/output/{document_id}_guide.json
    guide_name = f"{document_id}_guide.json"
    guide_candidates = [
        PROJECT_ROOT.parent / "output" / guide_name,
        PROJECT_ROOT / "output" / guide_name,
        Path("../../output") / guide_name,
        Path("../output") / guide_name,
    ]
    guide_path = next((p for p in guide_candidates if p.exists()), guide_candidates[0])
    if not guide_path.exists():
        print(f"  WARNING: Guide file not found at {guide_path}")
        return []
    with open(guide_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # The guide is a list of steps. Each step has fields like:
    # step_number, section_to_read, objective, questions_to_answer,
    # expected_output, needs_figures, needs_tables
    # Return the list of steps directly
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    # Direct top-level shapes
    top_level_steps = data.get("steps")
    if isinstance(top_level_steps, list):
        return top_level_steps

    guide_value = data.get("guide")
    if isinstance(guide_value, list):
        return guide_value
    if isinstance(guide_value, dict):
        nested_steps = guide_value.get("steps")
        if isinstance(nested_steps, list):
            return nested_steps

    # Pass-based shape (e.g. pass1_quick_scan.steps, pass2_*.steps, ...)
    collected_steps: list[dict[str, Any]] = []
    for value in data.values():
        if not isinstance(value, dict):
            continue
        maybe_steps = value.get("steps")
        if not isinstance(maybe_steps, list):
            continue
        for step in maybe_steps:
            if isinstance(step, dict):
                collected_steps.append(step)

    return collected_steps


def export_for_annotation() -> None:
    pipeline = RetrievalPipeline()
    can_filter_content_type = _content_type_filter_supported(pipeline)
    if not can_filter_content_type:
        print(
            "WARNING: Qdrant payload index for 'content_type' not found; "
            "figure/table context retrieval will be skipped."
        )

    export_rows: list[dict[str, Any]] = []
    per_paper_summary: dict[str, dict[str, Any]] = {}

    for paper in PAPERS:
        paper_id = str(paper.get("paper_id") or "")
        paper_type = str(paper.get("paper_type") or "")
        document_id = str(paper.get("document_id") or "").strip()

        if not document_id:
            print(f"Skipping {paper_id}: document_id is empty in evaluation/config.py")
            per_paper_summary[paper_id] = {
                "document_id": document_id,
                "guide_steps_found": 0,
                "sections_resolved": 0,
                "sections_with_figures": 0,
                "sections_with_tables": 0,
                "total_entries_exported": 0,
            }
            continue

        steps = load_guide(document_id)
        if not steps:
            print(f"Skipping {paper_id}: no guide steps found for document_id={document_id}")
            per_paper_summary[paper_id] = {
                "document_id": document_id,
                "guide_steps_found": 0,
                "sections_resolved": 0,
                "sections_with_figures": 0,
                "sections_with_tables": 0,
                "total_entries_exported": 0,
            }
            continue

        exported_count = 0
        sections_resolved = 0
        sections_with_figures = 0
        sections_with_tables = 0

        for step in steps:
            if not isinstance(step, dict):
                continue

            step_number = step.get("step_number")
            objective = str(step.get("objective") or "").strip()
            expected_output = str(step.get("expected_output") or "").strip()

            guide_step_title = str(step.get("guide_step_title") or "").strip()
            if not guide_step_title:
                if objective:
                    guide_step_title = (
                        f"Step {step_number}: {objective}" if step_number is not None else objective
                    )
                else:
                    guide_step_title = f"Step {step_number}" if step_number is not None else "Step"

            guide_step_description = str(step.get("guide_step_description") or "").strip()
            if not guide_step_description:
                guide_step_description = objective or expected_output

            guide_questions_raw = step.get("questions_to_answer") or []
            guide_questions = (
                [str(q).strip() for q in guide_questions_raw if str(q).strip()]
                if isinstance(guide_questions_raw, list)
                else []
            )

            section_labels_raw = step.get("section_to_read") or []
            section_labels = (
                [str(s).strip() for s in section_labels_raw if str(s).strip()]
                if isinstance(section_labels_raw, list)
                else []
            )

            needs_figures = bool(step.get("needs_figures", False))
            needs_tables = bool(step.get("needs_tables", False))

            for section_label in section_labels:
                query_results = pipeline.query(
                    query=section_label,
                    document_id=document_id,
                    top_k=3,
                    rerank=False,
                )
                section_id = None
                section_title = section_label
                if query_results:
                    section_id, section_title = _resolve_section_from_results(
                        pipeline=pipeline,
                        query_results=query_results,
                        section_label=section_label,
                    )

                if not section_id:
                    print(
                        f"  WARNING: Could not resolve section_id for '{section_label}' "
                        f"in paper {paper_id} ({document_id})"
                    )
                    continue

                sections_resolved += 1
                if needs_figures:
                    sections_with_figures += 1
                if needs_tables:
                    sections_with_tables += 1

                chunks = pipeline.retrieve_with_section_scope(
                    query=guide_step_title,
                    section_id=section_id,
                    document_id=document_id,
                    top_k=10,
                    rerank=True,
                )

                chunk_ids = [
                    chunk.metadata["_id"]
                    for chunk in chunks
                    if hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict) and chunk.metadata.get("_id")
                ]

                section_context = "\n\n".join(
                    chunk.content for chunk in chunks if hasattr(chunk, "content") and chunk.content
                )

                figure_chunks = []
                if needs_figures and can_filter_content_type:
                    try:
                        figure_chunks = pipeline.retrieve_by_content_type(
                            document_id=document_id,
                            section_id=section_id,
                            content_type="figure",
                            top_k=5,
                        )
                    except Exception as exc:
                        print(
                            f"  WARNING: Figure retrieval failed for section_id={section_id} "
                            f"in paper {paper_id}: {exc}"
                        )

                table_chunks = []
                if needs_tables and can_filter_content_type:
                    try:
                        table_chunks = pipeline.retrieve_by_content_type(
                            document_id=document_id,
                            section_id=section_id,
                            content_type="table",
                            top_k=5,
                        )
                    except Exception as exc:
                        print(
                            f"  WARNING: Table retrieval failed for section_id={section_id} "
                            f"in paper {paper_id}: {exc}"
                        )

                figure_context = "\n\n".join(
                    str(getattr(chunk, "content", "") or "").strip()
                    for chunk in figure_chunks
                    if str(getattr(chunk, "content", "") or "").strip()
                )

                table_context = "\n\n".join(
                    str(getattr(chunk, "content", "") or "").strip()
                    for chunk in table_chunks
                    if str(getattr(chunk, "content", "") or "").strip()
                )

                figure_chunk_ids = [
                    chunk.metadata["_id"]
                    for chunk in figure_chunks
                    if hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict) and chunk.metadata.get("_id")
                ]

                table_chunk_ids = [
                    chunk.metadata["_id"]
                    for chunk in table_chunks
                    if hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict) and chunk.metadata.get("_id")
                ]

                export_rows.append(
                    {
                        "paper_id": paper_id,
                        "paper_type": paper_type,
                        "document_id": document_id,
                        "section_id": section_id,
                        "section_title": section_title,
                        "guide_step_number": step_number,
                        "guide_step_title": guide_step_title,
                        "guide_step_description": guide_step_description,
                        "guide_questions": guide_questions,
                        "section_context": section_context,
                        "chunk_ids": chunk_ids,
                        "figure_context": figure_context,
                        "figure_chunk_ids": figure_chunk_ids,
                        "table_context": table_context,
                        "table_chunk_ids": table_chunk_ids,
                        "needs_figures": needs_figures,
                        "needs_tables": needs_tables,
                    }
                )
                exported_count += 1

        per_paper_summary[paper_id] = {
            "document_id": document_id,
            "guide_steps_found": len(steps),
            "sections_resolved": sections_resolved,
            "sections_with_figures": sections_with_figures,
            "sections_with_tables": sections_with_tables,
            "total_entries_exported": exported_count,
        }

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EXPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(export_rows, f, indent=2, ensure_ascii=False)

    print("\nExport summary:")
    for paper in PAPERS:
        paper_id = str(paper.get("paper_id") or "")
        stats = per_paper_summary.get(
            paper_id,
            {
                "document_id": str(paper.get("document_id") or "").strip(),
                "guide_steps_found": 0,
                "sections_resolved": 0,
                "sections_with_figures": 0,
                "sections_with_tables": 0,
                "total_entries_exported": 0,
            },
        )
        print(f"{paper_id} ({stats['document_id']}):")
        print(f"  Guide steps found: {stats['guide_steps_found']}")
        print(f"  Sections resolved: {stats['sections_resolved']}")
        print(f"  Sections with figures: {stats['sections_with_figures']}")
        print(f"  Sections with tables: {stats['sections_with_tables']}")
        print(f"  Total entries exported: {stats['total_entries_exported']}")
    print(f"\nSaved: {EXPORT_PATH}")


def main() -> None:
    export_for_annotation()


if __name__ == "__main__":
    main()
