import os
import sys

from dotenv import load_dotenv

from backend.extraction.persistence import PostgresPaperStore


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


def _resolve_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return dsn

    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    db = os.getenv("PG_DB", "research_agent")
    user = os.getenv("PG_USER", "postgres")
    pwd = os.getenv("PG_PASSWORD", "")
    if pwd:
        return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{db}"
    return f"postgresql+psycopg://{user}@{host}:{port}/{db}"


PAPER_NAME = os.getenv("PAPER_NAME", "")
store = PostgresPaperStore(_resolve_dsn())

paper = store.get_paper_by_name(PAPER_NAME) if PAPER_NAME else None
if paper is None:
    papers = store.list_papers(limit=1)
    if not papers:
        print("No papers found.")
        raise SystemExit(0)
    paper = store.get_paper_by_id(papers[0]["id"])

paper_id = int(paper["id"])
print("=== Paper ===")
print(f"  id         : {paper_id}")
print(f"  name       : {paper.get('paper_name')}")
print(f"  title      : {paper.get('title')}")
print(f"  created_at : {paper.get('created_at')}")

sections = store.get_sections_for_paper_id(paper_id)
print(f"\n=== Sections ({len(sections)}) ===")
for s in sections:
    level = int(s.get("level") or 1)
    indent = "  " * max(level - 1, 0)
    print(f"  {indent}[L{level}] {s.get('original_name')}  (id={s.get('id')})")

intro = next(
    (s for s in sections if "introduction" in (s.get("original_name") or "").lower()),
    None,
)
if intro:
    section_id = int(intro["id"])
    rows = [
        r
        for r in store.get_section_text_blocks_for_paper_id(paper_id)
        if int(r["section_id"]) == section_id
    ]
    print(
        f"\n=== Text Blocks in '{intro.get('original_name')}' (section_id={section_id}) ==="
    )
    print(f"  Total blocks: {len(rows)}\n")
    for row in rows:
        text = row.get("text_content") or ""
        print(f"  page={row.get('page_number')} block_id={row.get('text_block_db_id')}")
        print(f"  {text[:300]}")
        print()
else:
    print("\n  No 'Introduction' section found.")
