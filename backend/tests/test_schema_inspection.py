"""
Check the actual database schema that's being used.
"""

import sys
import logging
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND_DIR.parent
for _p in (_PROJECT_ROOT, _BACKEND_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text, inspect
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


database_url = os.getenv("DATABASE_URL") or "postgresql+psycopg://postgres@localhost:5432/research_agent"

engine = create_engine(database_url, pool_pre_ping=True)
inspector = inspect(engine)

print("\n" + "=" * 80)
print("ACTUAL DATABASE SCHEMA")
print("=" * 80)

with engine.connect() as conn:
    # Check documents table
    if 'documents' in inspector.get_table_names():
        print("\n✓ documents table:")
        columns = inspector.get_columns('documents')
        for col in columns:
            print(f"  ├─ {col['name']:30} {col['type']}")
        
        result = conn.execute(text("SELECT COUNT(*) FROM documents"))
        count = result.scalar()
        print(f"  └─ Total records: {count}")
        
        if count > 0:
            result = conn.execute(text(
                "SELECT id, title FROM documents ORDER BY id DESC LIMIT 3"
            ))
            print(f"  └─ Sample documents:")
            for row in result:
                title = (row[1] or "N/A")[:60] if row[1] else "N/A"
                print(f"      ├─ [{row[0]}] {title}")
    
    # Check sections table
    if 'sections' in inspector.get_table_names():
        print("\n✓ sections table:")
        columns = inspector.get_columns('sections')
        for col in columns:
            print(f"  ├─ {col['name']:30} {col['type']}")
        
        result = conn.execute(text("SELECT COUNT(*) FROM sections"))
        count = result.scalar()
        print(f"  └─ Total records: {count}")
        
        if count > 0:
            result = conn.execute(text(
                "SELECT id, document_id, title, level FROM sections LIMIT 5"
            ))
            print(f"  └─ Sample sections:")
            for row in result:
                print(f"      ├─ [{row[0]}] doc_id={row[1]}, level={row[3]}: {row[2][:40]}")
    
    # Check text_blocks table
    if 'text_blocks' in inspector.get_table_names():
        print("\n✓ text_blocks table:")
        columns = inspector.get_columns('text_blocks')
        for col in columns:
            print(f"  ├─ {col['name']:30} {col['type']}")
        
        result = conn.execute(text("SELECT COUNT(*) FROM text_blocks"))
        count = result.scalar()
        print(f"  └─ Total records: {count}")
    
    # Check document_tables
    if 'document_tables' in inspector.get_table_names():
        print("\n✓ document_tables table:")
        columns = inspector.get_columns('document_tables')
        for col in columns:
            print(f"  ├─ {col['name']:30} {col['type']}")
        
        result = conn.execute(text("SELECT COUNT(*) FROM document_tables"))
        count = result.scalar()
        print(f"  └─ Total records: {count}")
    
    # Check relationships
    print("\n" + "=" * 80)
    print("RELATIONSHIPS")
    print("=" * 80)
    
    result = conn.execute(text(
        "SELECT constraint_name, table_name, column_name, foreign_table_name, foreign_column_name "
        "FROM information_schema.key_column_usage "
        "WHERE table_schema = 'public' AND foreign_table_name IS NOT NULL"
    ))
    
    print("\nForeign Keys:")
    for row in result:
        print(f"  ├─ {row[1]}.{row[2]} -> {row[3]}.{row[4]}")

print("\n" + "=" * 80)
print("SAMPLE DATA")
print("=" * 80)

with engine.connect() as conn:
    # Get first document with sections
    result = conn.execute(text(
        "SELECT d.id, d.title FROM documents d ORDER BY d.id DESC LIMIT 1"
    ))
    doc = result.first()
    
    if doc:
        doc_id, doc_title = doc
        print(f"\nDocument: {doc_title}")
        
        result = conn.execute(text(
            "SELECT id, title, level, section_id FROM sections WHERE document_id = :doc_id ORDER BY section_id"
        ),
        {'doc_id': doc_id}
        )
        
        sections = result.fetchall()
        if sections:
            print(f"Sections ({len(sections)} total):")
            for sec_id, sec_title, level, section_id_col in sections[:20]:
                indent = "  " * level
                print(f"{indent}├─ [{sec_id}] {section_id_col}: {sec_title[:50]}")
            
            # Find introduction/conclusion
            print("\n" + "-" * 80)
            for sec_id, sec_title, level, sid in sections:
                title_lower = sec_title.lower()
                if 'introduction' in title_lower:
                    print(f"✓ Found INTRODUCTION: {sec_title} (ID: {sec_id})")
                elif 'conclusion' in title_lower:
                    print(f"✓ Found CONCLUSION: {sec_title} (ID: {sec_id})")

print("\n" + "=" * 80)
