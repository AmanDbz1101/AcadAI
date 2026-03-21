"""Generate a manual QA dataset template from indexed paper sections.

This script does not generate questions or answers automatically.
It only creates placeholders for manual completion.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


# Ensure the backend package root is importable when running from project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT
if str(BACKEND_DIR) not in sys.path:
	sys.path.insert(0, str(BACKEND_DIR))

from rag.retrieval import RetrievalPipeline
from evaluation.config import PAPERS


TEMPLATE_OUTPUT_PATH = PROJECT_ROOT / "evaluation" / "dataset" / "qa_pairs_template.json"
SECTION_DISCOVERY_QUERY = "method result contribution"
SECTION_DISCOVERY_TOP_K = 200
PLACEHOLDERS_PER_SECTION = 3


def _collect_unique_sections(pipeline: RetrievalPipeline, document_id: str) -> list[dict[str, str]]:
	"""Return unique sections for one document, deduplicated by metadata.section_id."""
	results = pipeline.query(
		query=SECTION_DISCOVERY_QUERY,
		document_id=document_id,
		top_k=SECTION_DISCOVERY_TOP_K,
		rerank=False,
	)

	sections_by_id: dict[str, dict[str, str]] = {}
	for result in results:
		metadata = result.metadata if isinstance(result.metadata, dict) else {}
		section_id = metadata.get("section_id")
		if not section_id:
			continue

		if section_id not in sections_by_id:
			sections_by_id[section_id] = {
				"section_id": str(section_id),
				"section_title": str(metadata.get("section_title") or ""),
			}

	return list(sections_by_id.values())


def _make_placeholder_entries(paper: dict, sections: list[dict[str, str]]) -> list[dict]:
	"""Create 3 manual-fill placeholders per section."""
	entries: list[dict] = []

	for section in sections:
		for _ in range(PLACEHOLDERS_PER_SECTION):
			entries.append(
				{
					"paper_id": paper.get("paper_id", ""),
					"paper_type": paper.get("paper_type", ""),
					"document_id": paper.get("document_id", ""),
					"section_id": section["section_id"],
					"section_title": section["section_title"],
					"question": "FILL IN: specific question answerable only from this section",
					"reference_answer": "FILL IN: 2-4 sentence answer written from section text",
					"relevant_chunk_ids": ["FILL IN: chunk_id values from retrieval"],
					"question_type": "FILL IN: factual OR conceptual OR comparative",
				}
			)

	return entries


def main() -> None:
	pipeline = RetrievalPipeline()
	all_entries: list[dict] = []
	paper_summaries: list[dict] = []

	for paper in PAPERS:
		paper_id = paper.get("paper_id", "")
		document_id = (paper.get("document_id") or "").strip()

		if not document_id:
			paper_summaries.append(
				{
					"paper_id": paper_id,
					"sections": 0,
					"entries": 0,
					"status": "skipped (empty document_id)",
				}
			)
			continue

		sections = _collect_unique_sections(pipeline, document_id)
		paper_entries = _make_placeholder_entries(paper, sections)
		all_entries.extend(paper_entries)

		paper_summaries.append(
			{
				"paper_id": paper_id,
				"sections": len(sections),
				"entries": len(paper_entries),
				"status": "ok",
			}
		)

	TEMPLATE_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
	with TEMPLATE_OUTPUT_PATH.open("w", encoding="utf-8") as f:
		json.dump(all_entries, f, indent=2, ensure_ascii=False)

	print("Dataset template generation complete.")
	print(f"Output file: {TEMPLATE_OUTPUT_PATH}")
	print("\nPer-paper summary:")
	for summary in paper_summaries:
		print(
			f"- {summary['paper_id']}: "
			f"sections={summary['sections']}, entries={summary['entries']} "
			f"[{summary['status']}]"
		)

	print("\nNext steps:")
	print("1. Open evaluation/dataset/qa_pairs_template.json")
	print("2. Fill in every field marked 'FILL IN'")
	print("3. Save the completed file as evaluation/dataset/qa_pairs.json")


if __name__ == "__main__":
	main()
