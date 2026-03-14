import os
import uuid
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor


TABLE_NAME = "text_extraction_documents"


def get_db_url() -> str:
    return os.getenv(
        "TEXT_EXTRACTION_DB_URL",
        os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/research_agent"),
    )


@contextmanager
def get_connection():
    conn = psycopg2.connect(get_db_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f'''
                    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                        id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        collection_name TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                '''
            )

def add_document(filename: str, collection_name: str) -> str:
    """
    Adds a document record and returns the generated UUID.
    """
    doc_id = str(uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {TABLE_NAME} (id, filename, collection_name) VALUES (%s, %s, %s)",
                (doc_id, filename, collection_name),
            )
    return doc_id

def get_document(doc_id: str):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"SELECT id, filename, collection_name, created_at FROM {TABLE_NAME} WHERE id = %s",
                (doc_id,),
            )
            row = cursor.fetchone()
    if row:
        return {
            "id": row["id"],
            "filename": row["filename"],
            "collection_name": row["collection_name"],
            "created_at": row["created_at"],
        }
    return None

def get_all_documents():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                f"SELECT id, filename, collection_name, created_at FROM {TABLE_NAME}"
            )
            rows = cursor.fetchall()
    return [
        {
            "id": row["id"],
            "filename": row["filename"],
            "collection_name": row["collection_name"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]

# Initialize DB on import
init_db()
