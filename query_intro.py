import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from backend.database.connection import DatabaseConnection
from backend.database.repository import DocumentRepository

DOC_ID = "2f5cdbf0-49e0-46af-8bdc-d861443d92c7"
db = DatabaseConnection()

with db.session() as sess:
    repo = DocumentRepository(sess)

    # --- Stats ---
    stats = repo.get_document_stats(DOC_ID)
    print("=== Document Stats ===")
    for k, v in stats.items():
        print(f"  {k:<15}: {v}")

    # --- All Sections ---
    sections = repo.get_sections_for_document(DOC_ID)
    print(f"\n=== Sections ({len(sections)}) ===")
    for s in sections:
        indent = "  " * (s.level - 1)
        print(f"  {indent}[L{s.level}] {s.numbering or ''} {s.title}  (id={s.id})")

    # --- Introduction text blocks ---
    intro = next((s for s in sections if "introduction" in s.title.lower()), None)
    if intro:
        print(f"\n=== Text Blocks in '{intro.title}' (section_id={intro.id}) ===")
        blocks = repo.get_text_blocks_for_section(intro.id)
        print(f"  Total blocks: {len(blocks)}\n")
        for b in blocks:
            print(f"  [{b.label}] page={b.page_number} order={b.reading_order}")
            print(f"  {b.content[:300]}")
            print()
    else:
        print("\n  No 'Introduction' section found.")
