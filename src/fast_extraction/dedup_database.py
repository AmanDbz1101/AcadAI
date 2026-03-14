"""
SQL database for document deduplication and tracking
"""

import os
import hashlib
import uuid
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from .models import DocumentRecord, DocumentStatus


class DeduplicationDatabase:
    """Manages document deduplication and status tracking"""
    
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv(
            "FAST_EXTRACTION_DB_URL",
            os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/research_agent"),
        )
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        id BIGSERIAL PRIMARY KEY,
                        document_id TEXT UNIQUE NOT NULL,
                        pdf_hash TEXT NOT NULL,
                        title TEXT NOT NULL,
                        status TEXT NOT NULL,
                        docling_metadata_path TEXT,
                        api_metadata_path TEXT,
                        vectorstore_collection TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create indexes for fast lookups
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pdf_hash 
                    ON documents(pdf_hash)
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_document_id 
                    ON documents(document_id)
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_status 
                    ON documents(status)
                """)
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = psycopg2.connect(self.db_url)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def compute_pdf_hash(self, pdf_path: str) -> str:
        """
        Compute SHA256 hash of PDF file
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Hexadecimal hash string
        """
        sha256_hash = hashlib.sha256()
        with open(pdf_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def check_document(self, pdf_hash: str) -> Optional[DocumentRecord]:
        """
        Check if document already exists by hash
        
        Args:
            pdf_hash: PDF file hash
            
        Returns:
            DocumentRecord if exists, None otherwise
        """
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM documents WHERE pdf_hash = %s
                    """,
                    (pdf_hash,),
                )
            
            row = cursor.fetchone()
            if row:
                return self._row_to_record(row)
            return None
    
    def get_document_by_id(self, document_id: str) -> Optional[DocumentRecord]:
        """
        Get document by document_id
        
        Args:
            document_id: UUID document identifier
            
        Returns:
            DocumentRecord if exists, None otherwise
        """
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM documents WHERE document_id = %s
                    """,
                    (document_id,),
                )
            
            row = cursor.fetchone()
            if row:
                return self._row_to_record(row)
            return None
    
    def insert_document(
        self,
        pdf_hash: str,
        title: str,
        status: DocumentStatus = DocumentStatus.PROCESSING,
        document_id: Optional[str] = None
    ) -> str:
        """
        Insert new document record
        
        Args:
            pdf_hash: PDF file hash
            title: Paper title
            status: Initial status
            document_id: Optional custom document_id (generates UUID if None)
            
        Returns:
            document_id (UUID string)
        """
        if document_id is None:
            document_id = str(uuid.uuid4())
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO documents (
                        document_id, pdf_hash, title, status
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (document_id, pdf_hash, title, status.value),
                )
        
        return document_id
    
    def update_status(
        self,
        document_id: str,
        status: DocumentStatus,
        title: Optional[str] = None,
        docling_metadata_path: Optional[str] = None,
        api_metadata_path: Optional[str] = None,
        vectorstore_collection: Optional[str] = None
    ) -> bool:
        """
        Update document status and metadata paths
        
        Args:
            document_id: Document UUID
            status: New status
            title: Updated paper title
            docling_metadata_path: Path to docling metadata JSON
            api_metadata_path: Path to API metadata JSON
            vectorstore_collection: Qdrant collection name
            
        Returns:
            True if updated, False if not found
        """
        with self._get_connection() as conn:
            updates = ["status = ?"]
            params = [status.value]
            
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            
            if docling_metadata_path is not None:
                updates.append("docling_metadata_path = ?")
                params.append(docling_metadata_path)
            
            if api_metadata_path is not None:
                updates.append("api_metadata_path = ?")
                params.append(api_metadata_path)
            
            if vectorstore_collection is not None:
                updates.append("vectorstore_collection = ?")
                params.append(vectorstore_collection)
            
            params.append(document_id)

            updates = [u.replace("?", "%s") for u in updates]

            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE documents 
                    SET {', '.join(updates)}
                    WHERE document_id = %s
                    """,
                    params,
                )
            return cursor.rowcount > 0
    
    def get_all_documents(
        self,
        status: Optional[DocumentStatus] = None,
        limit: Optional[int] = None
    ) -> List[DocumentRecord]:
        """
        Get all documents, optionally filtered by status
        
        Args:
            status: Filter by status (None = all)
            limit: Maximum number of results
            
        Returns:
            List of DocumentRecord objects
        """
        with self._get_connection() as conn:
            query = "SELECT * FROM documents"
            params = []
            
            if status:
                query += " WHERE status = %s"
                params.append(status.value)
            
            query += " ORDER BY created_at DESC"
            
            if limit:
                query += " LIMIT %s"
                params.append(limit)

            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
            
            return [self._row_to_record(row) for row in rows]
    
    def delete_document(self, document_id: str) -> bool:
        """
        Delete document record
        
        Args:
            document_id: Document UUID
            
        Returns:
            True if deleted, False if not found
        """
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM documents WHERE document_id = %s
                    """,
                    (document_id,),
                )
            return cursor.rowcount > 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get database statistics
        
        Returns:
            Dict with counts by status
        """
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as processing,
                        SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as docling_ready,
                        SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as api_complete,
                        SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) as failed
                    FROM documents
                    """,
                    (
                        DocumentStatus.PROCESSING.value,
                        DocumentStatus.DOCLING_READY.value,
                        DocumentStatus.API_COMPLETE.value,
                        DocumentStatus.FAILED.value,
                    ),
                )
            
            row = cursor.fetchone()
            return {
                "total": row["total"],
                "processing": row["processing"],
                "docling_ready": row["docling_ready"],
                "api_complete": row["api_complete"],
                "failed": row["failed"]
            }
    
    def _row_to_record(self, row: Dict[str, Any]) -> DocumentRecord:
        """Convert database row to DocumentRecord"""
        return DocumentRecord(
            id=row["id"],
            document_id=row["document_id"],
            pdf_hash=row["pdf_hash"],
            title=row["title"],
            status=DocumentStatus(row["status"]),
            docling_metadata_path=row["docling_metadata_path"],
            api_metadata_path=row["api_metadata_path"],
            vectorstore_collection=row["vectorstore_collection"],
            created_at=row["created_at"],
        )
