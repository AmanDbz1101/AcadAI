"""Helper script to fetch chunk IDs for a section-scoped question."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rag.retrieval import RetrievalPipeline  # type: ignore[import-not-found]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve section-scoped chunks and print chunk_id values."
    )
    parser.add_argument("--document_id", required=True, help="Qdrant document_id")
    parser.add_argument("--section_id", required=True, help="Section ID to scope retrieval")
    parser.add_argument("--question", required=True, help="Question/query text")
    parser.add_argument(
        "--top_k",
        type=int,
        default=10,
        help="Number of chunks to retrieve (default: 10)",
    )
    return parser.parse_args()


def _preview(text: str, max_chars: int = 120) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "..."


def main() -> None:
    args = parse_args()

    pipeline = RetrievalPipeline()
    results = pipeline.retrieve_with_section_scope(
        query=args.question,
        section_id=args.section_id,
        document_id=args.document_id,
        top_k=args.top_k,
        rerank=True,
    )

    for idx, result in enumerate(results, 1):
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        chunk_id = metadata.get("chunk_id", "")
        section_title = metadata.get("section_title", "")
        content_type = metadata.get("content_type", "")

        print(f"[{idx}] chunk_id: {chunk_id}")
        print(f"    score: {result.score:.3f}")
        print(f"    section: {section_title}")
        print(f"    content_type: {content_type}")
        print(f"    preview: {_preview(result.content)}")
        print()

    print(
        "Copy the chunk_id values of relevant chunks into your relevant_chunk_ids field in qa_pairs_template.json"
    )


if __name__ == "__main__":
    main()
