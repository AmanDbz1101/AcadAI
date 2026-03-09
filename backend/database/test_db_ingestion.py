"""
Quick smoke-test for the DB ingestion pipeline.

Run from the project root::

    source env_research/bin/activate
    python backend/database/test_db_ingestion.py ../input/<paper>.pdf

This does NOT run the full LangGraph pipeline (no LLM calls).
It exercises only:
  1. DoclingRichExtractor  – Docling conversion + rich element extraction
  2. DBIngestionPipeline   – writing everything to PostgreSQL
  3. DocumentRepository    – reading back the stored data

Usage::

    python backend/database/test_db_ingestion.py input/MemGPT.pdf
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

# Make sure project root is on the path
_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv()

from backend.database.connection import DatabaseConnection
from backend.database.repository import DocumentRepository
from backend.extraction.app.docling_rich_extractor import DoclingRichExtractor
from backend.extraction.pipelines.db_ingestion_pipeline import DBIngestionPipeline


def main(pdf_path: str) -> None:
    pdf = Path(pdf_path)
    assert pdf.exists(), f"PDF not found: {pdf}"

    print(f"\n{'='*60}")
    print(f"  DB Ingestion Smoke-Test")
    print(f"  PDF : {pdf.name}")
    print(f"{'='*60}\n")

    # --- Connect ---
    db = DatabaseConnection()
    db.create_tables()
    assert db.health_check(), "DB is not reachable — check DATABASE_URL in .env"
    print("✓  Database reachable")

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
    pipeline = DBIngestionPipeline(db_connection=db)
    stored_id = pipeline.ingest(
        pdf_path=pdf,
        document_id=doc_id,
        rich_result=rich,
        skip_if_exists=False,  # allow re-run in tests
    )
    print(f"\n✓  Ingested document  id={stored_id}")

    # --- Read back ---
    with db.session() as sess:
        repo = DocumentRepository(sess)
        stats = repo.get_document_stats(stored_id)
        print(f"\n  DB stats for document:")
        for k, v in stats.items():
            print(f"     {k:<15} : {v}")

        blocks = repo.get_text_blocks_for_document(stored_id)
        if blocks:
            sample = blocks[0]
            print(f"\n  First text block:")
            print(f"     page     : {sample.page_number}")
            print(f"     label    : {sample.label}")
            print(f"     section  : {sample.section_title!r}")
            print(f"     bbox     : l={sample.bbox_l} t={sample.bbox_t} r={sample.bbox_r} b={sample.bbox_b}")
            print(f"     content  : {sample.content[:120]!r}")

    print(f"\n✓  Smoke test passed\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backend/database/test_db_ingestion.py <path/to/paper.pdf>")
        sys.exit(1)
    main(sys.argv[1])
