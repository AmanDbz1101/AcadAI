"""Query stored paper artifacts from PostgreSQL by paper name."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

_HERE = Path(__file__).resolve().parent
_BACKEND_DIR = _HERE.parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent
for _p in (_PROJECT_ROOT, _BACKEND_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from backend.extraction.persistence import PostgresPaperStore


def _resolve_postgres_dsn() -> str:
    dsn = os.getenv("POSTGRES_DSN")
    if dsn:
        return dsn

    host = os.getenv("POSTGRES_HOST") or os.getenv("PGHOST")
    port = os.getenv("POSTGRES_PORT") or os.getenv("PGPORT")
    dbname = os.getenv("POSTGRES_DB") or os.getenv("PGDATABASE")
    user = os.getenv("POSTGRES_USER") or os.getenv("PGUSER")
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD")

    if not all([host, port, dbname, user]):
        raise ValueError(
            "PostgreSQL configuration not found. Set POSTGRES_DSN or POSTGRES_HOST/PORT/DB/USER."
        )

    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    return f"postgresql://{user}@{host}:{port}/{dbname}"


def fetch_bundle(store: PostgresPaperStore, paper_name: str) -> Dict[str, Any]:
    paper = store.get_paper_by_name(paper_name)
    if not paper:
        return {
            "paper": None,
            "sections": [],
            "text_blocks": [],
            "tables": [],
            "images": [],
            "references": [],
        }

    return {
        "paper": paper,
        "sections": store.get_sections_for_paper(paper_name),
        "text_blocks": store.get_text_blocks_for_paper(paper_name),
        "tables": store.get_tables_for_paper(paper_name),
        "images": store.get_images_for_paper(paper_name),
        "references": store.get_references_for_paper(paper_name),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Query extracted paper artifacts from PostgreSQL")
    parser.add_argument("paper_name", help="Paper title/name used for lookup")
    parser.add_argument("--out", help="Optional JSON output file path")
    parser.add_argument("--summary", action="store_true", help="Print compact counts only")
    args = parser.parse_args()

    dsn = _resolve_postgres_dsn()
    store = PostgresPaperStore(dsn)

    bundle = fetch_bundle(store, args.paper_name)
    if bundle["paper"] is None:
        print(f"Paper not found: {args.paper_name}")
        return 1

    if args.summary:
        print("paper_name:", bundle["paper"].get("paper_name"))
        print("paper_id:", bundle["paper"].get("id"))
        print("sections:", len(bundle["sections"]))
        print("text_blocks:", len(bundle["text_blocks"]))
        print("tables:", len(bundle["tables"]))
        print("images:", len(bundle["images"]))
        print("references:", len(bundle["references"]))
    else:
        print(json.dumps(bundle, indent=2, default=str, ensure_ascii=False))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(bundle, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
        print(f"Saved JSON to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
