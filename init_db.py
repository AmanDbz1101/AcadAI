#!/usr/bin/env python3
"""
Database initialization script.

Creates all tables defined in the schema using SQLAlchemy.
"""

import sys
import os
from sqlalchemy import create_engine

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.extraction.persistence.postgres_store import Base

def main():
    if len(sys.argv) != 2:
        print("❌ Usage: python init_db.py <password>")
        sys.exit(1)

    password = sys.argv[1]

    # Build DSN
    dsn = f"postgresql+psycopg2://anjal:{password}@localhost:5432/research_agent"

    print("🔌 Connecting to database...")
    try:
        engine = create_engine(dsn, pool_pre_ping=True)
        # Test connection
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        print("✅ Database connection successful.")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)

    print("📋 Creating tables...")
    try:
        Base.metadata.create_all(engine)
        print("✅ All tables created successfully.")
    except Exception as e:
        print(f"❌ Failed to create tables: {e}")
        sys.exit(1)

    # List of tables created
    tables = [
        "papers",
        "users",
        "sections",
        "text_blocks",
        "tables_data",
        "images",
        "references_data",
        "section_text_blocks",
        "section_tables",
        "section_images",
        "user_papers",
        "paper_guides",
        "paper_questions"
    ]

    print("📊 Tables created:")
    for table in tables:
        print(f"   ✓ {table}")

if __name__ == "__main__":
    main()