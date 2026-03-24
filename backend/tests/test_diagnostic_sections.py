"""
Diagnostic test - check what's actually in the database without creating tables.

This helps understand the current schema and what section data exists.
"""

import sys
import logging
from pathlib import Path
from typing import Optional

# Setup path
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND_DIR.parent
for _p in (_PROJECT_ROOT, _BACKEND_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_database_url() -> str:
    """Build PostgreSQL DSN from environment variables."""
    import os
    
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    db   = os.getenv("PG_DB",   "research_agent")
    user = os.getenv("PG_USER", "postgres")
    pwd  = os.getenv("PG_PASSWORD", "")

    if pwd:
        return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{db}"
    return f"postgresql+psycopg://{user}@{host}:{port}/{db}"


def main():
    database_url = _build_database_url()
    
    print("\n" + "=" * 80)
    print("DATABASE DIAGNOSTIC TEST")
    print("=" * 80)
    
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        Session = sessionmaker(bind=engine)
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✓ Database connection successful")
        
        # Inspect schema
        inspector = inspect(engine)
        
        # List all tables
        tables = inspector.get_table_names()
        print(f"\n✓ Tables in database ({len(tables)}):")
        for table in sorted(tables):
            print(f"  ├─ {table}")
        
        # Check if papers table exists
        if 'papers' in tables:
            print("\n✓ Papers table found")
            with engine.connect() as conn:
                # Count papers
                result = conn.execute(text("SELECT COUNT(*) as count FROM papers"))
                count = result.scalar()
                print(f"  ├─ Total papers: {count}")
                
                # Get recent papers
                if count > 0:
                    result = conn.execute(text(
                        "SELECT id, paper_name, title FROM papers ORDER BY created_at DESC LIMIT 5"
                    ))
                    print(f"  ├─ Recent papers:")
                    for row in result:
                        title = (row[2] or "N/A")[:50]
                        print(f"  │   ├─ [{row[0]}] {row[1]} - {title}")
        else:
            print("\n✗ Papers table not found - database may be empty or not initialized")
            return
        
        # Check sections table
        if 'sections' in tables:
            print("\n✓ Sections table found")
            with engine.connect() as conn:
                # Count sections
                result = conn.execute(text("SELECT COUNT(*) as count FROM sections"))
                count = result.scalar()
                print(f"  ├─ Total sections: {count}")
                
                # Check schema
                columns = inspector.get_columns('sections')
                print(f"  ├─ Columns:")
                for col in columns[:8]:  # Show first 8 columns
                    print(f"  │   ├─ {col['name']} ({col['type']})")
                
                # Get section sample
                if count > 0:
                    result = conn.execute(text(
                        "SELECT id, paper_id, original_name, level FROM sections LIMIT 5"
                    ))
                    print(f"  ├─ Sample sections:")
                    for row in result:
                        print(f"  │   ├─ [ID: {row[0]}] {row[3]}: {row[2]} (paper_id={row[1]})")
        else:
            print("\n✗ Sections table not found")
        
        # Check text_blocks table
        if 'text_blocks' in tables:
            print("\n✓ Text Blocks table found")
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) as count FROM text_blocks"))
                count = result.scalar()
                print(f"  ├─ Total text blocks: {count}")
        else:
            print("\n✗ Text Blocks table not found")
        
        # Check junction tables
        print("\n✓ Junction tables:")
        junction_tables = [
            'section_text_blocks',
            'section_tables',
            'section_images'
        ]
        for jt in junction_tables:
            if jt in tables:
                with engine.connect() as conn:
                    result = conn.execute(text(f"SELECT COUNT(*) as count FROM {jt}"))
                    count = result.scalar()
                    print(f"  ├─ {jt}: {count} records")
            else:
                print(f"  ├─ {jt}: NOT FOUND")
        
        # Try to get a paper with its sections
        print("\n" + "=" * 80)
        print("SAMPLE PAPER STRUCTURE")
        print("=" * 80)
        
        with engine.connect() as conn:
            # Get first paper
            result = conn.execute(text(
                "SELECT id, paper_name, title FROM papers ORDER BY created_at DESC LIMIT 1"
            ))
            paper = result.first()
            
            if paper:
                paper_id, paper_name, paper_title = paper
                print(f"\nPaper: {paper_name}")
                print(f"Title: {paper_title}")
                
                # Get sections for this paper
                result = conn.execute(text(
                    "SELECT id, original_name, level, page_start FROM sections "
                    "WHERE paper_id = :pid ORDER BY position"
                ),
                {'pid': paper_id}
                )
                
                sections = result.fetchall()
                if sections:
                    print(f"\nSections ({len(sections)} total):")
                    for sec_id, sec_name, level, page_start in sections[:15]:
                        indent = "  " * (level - 1)
                        print(f"{indent}├─ [{sec_id}] {sec_name} (Lvl{level}, p.{page_start})")
                    
                    if len(sections) > 15:
                        print(f"{len(sections) - 15} more sections...")
                    
                    # Find introduction and conclusion
                    print("\n" + "-" * 80)
                    print("KEY SECTIONS:")
                    for sec_id, sec_name, level, page_start in sections:
                        name_lower = sec_name.lower()
                        if 'introduction' in name_lower or 'intro' in name_lower:
                            print(f"✓ Introduction: {sec_name} (ID: {sec_id}, p.{page_start})")
                        elif 'conclusion' in name_lower or 'concluding' in name_lower:
                            print(f"✓ Conclusion: {sec_name} (ID: {sec_id}, p.{page_start})")
                else:
                    print("\nNo sections found for this paper")
            else:
                print("No papers found in database")
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "=" * 80)
    print("END DIAGNOSTIC")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
