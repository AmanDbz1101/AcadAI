"""
Quick smoke-test for the DB ingestion pipeline.

Run from the project root::

    source env_research/bin/activate
    python backend/database/test_db_ingestion.py ../input/<paper>.pdf

This does NOT run the full LangGraph pipeline (no LLM calls).
It exercises only:
  1. DoclingRichExtractor  – Docling conversion + rich element extraction
  2. DBIngestionPipeline   – writing everything to PostgreSQL
    3. PostgresPaperStore    – reading back the stored data

Usage::

    python backend/database/test_db_ingestion.py input/MemGPT.pdf
"""
from __future__ import annotations

import sys
import os
import uuid
from pathlib import Path

# Make sure project root is on the path
_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv()

from backend.extraction.app.docling_rich_extractor import DoclingRichExtractor
from backend.extraction.persistence import PostgresPaperStore
from backend.extraction.pipelines.db_ingestion_pipeline import DBIngestionPipeline


def main(pdf_path: str) -> None:
    pdf = Path(pdf_path)
    assert pdf.exists(), f"PDF not found: {pdf}"

    print(f"\n{'='*60}")
    print(f"  DB Ingestion Smoke-Test")
    print(f"  PDF : {pdf.name}")
    print(f"{'='*60}\n")

    # --- Extract rich data ---
    extractor = DoclingRichExtractor(extract_tables=True, extract_pictures=False)
    print("  Running DoclingRichExtractor …")
    rich = extractor.extract(pdf)

    print(f"✓  Extracted:")
    print(f"     pages        : {rich.total_pages}")
    print(f"     sections     : {len(rich.sections)}")
    print(f"     text blocks  : {len(rich.text_blocks)}")
    print(f"     tables       : {len(rich.tables)}")
    print(f"     figures      : {len(rich.figures)}")
    print(f"     formulas     : {len(rich.formulas)}")

    # --- Ingest ---
    doc_id = str(uuid.uuid4())
    pipeline = DBIngestionPipeline(rich_extractor=extractor)
    stored_id = pipeline.ingest(
        pdf_path=pdf,
        document_id=doc_id,
        rich_result=rich,
        skip_if_exists=False,  # allow re-run in tests
    )
    print(f"\n✓  Ingested document  id={stored_id}")

    # --- Read back ---
    dsn = (
        os.getenv("POSTGRES_DSN")
        or os.getenv("DATABASE_URL")
        or "postgresql+psycopg://postgres@localhost:5432/research_agent"
    )
    store = PostgresPaperStore(dsn)
    paper = store.get_paper_by_id(int(stored_id)) if stored_id.isdigit() else None
    if paper:
        print("\n  DB stats for paper:")
        print(f"     id              : {paper.get('id')}")
        print(f"     title           : {paper.get('title')}")
        print(f"     created_at      : {paper.get('created_at')}")

        blocks = store.get_text_blocks_for_paper_id(int(stored_id))
        if blocks:
            sample = blocks[0]
            print("\n  First text block:")
            print(f"     page     : {sample.get('page_number')}")
            print(f"     id       : {sample.get('element_id')}")
            print(f"     content  : {(sample.get('text_content') or '')[:120]!r}")

    print(f"\n✓  Smoke test passed\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backend/database/test_db_ingestion.py <path/to/paper.pdf>")
        sys.exit(1)
    main(sys.argv[1])
