import sqlite3
import uuid
import os

def get_db_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "documents.db")
    return db_path

def init_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            collection_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_document(filename: str, collection_name: str) -> str:
    """
    Adds a document record and returns the generated UUID.
    """
    doc_id = str(uuid.uuid4())
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('INSERT INTO documents (id, filename, collection_name) VALUES (?, ?, ?)', (doc_id, filename, collection_name))
    conn.commit()
    conn.close()
    return doc_id

def get_document(doc_id: str):
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT id, filename, collection_name, created_at FROM documents WHERE id = ?', (doc_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "filename": row[1],
            "collection_name": row[2],
            "created_at": row[3]
        }
    return None

def get_all_documents():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT id, filename, collection_name, created_at FROM documents')
    rows = c.fetchall()
    conn.close()
    return [
        {"id": row[0], "filename": row[1], "collection_name": row[2], "created_at": row[3]}
        for row in rows
    ]

# Initialize DB on import
init_db()
