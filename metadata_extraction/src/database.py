"""
SQL Database Manager for Research Paper Metadata Storage.

This module handles persistent storage of all extracted metadata including:
- Paper metadata (title, abstract, inference)
- Text blocks with full content and metadata
- Section information
- Extraction timestamps and file paths
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from metadata_extraction.src.models import PaperMetadata, SectionMetadata, PaperInference
from metadata_extraction.src.text_extraction import TextBlock


class DatabaseManager:
    """Manages SQLite database for research paper metadata storage."""
    
    def __init__(self, db_path: str = "research_papers.db"):
        """Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._initialize_database()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections.
        
        Yields:
            sqlite3.Connection: Database connection
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _initialize_database(self):
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Papers table - stores main paper metadata
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pdf_path TEXT UNIQUE NOT NULL,
                    pdf_filename TEXT NOT NULL,
                    title TEXT NOT NULL,
                    abstract TEXT,
                    paper_type TEXT,
                    difficulty TEXT,
                    math_heavy BOOLEAN,
                    extraction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Text blocks table - stores all extracted text blocks
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS text_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    element_type TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
                )
            """)
            
            # Sections table - stores detected sections
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id INTEGER NOT NULL,
                    section_name TEXT NOT NULL,
                    page_start INTEGER NOT NULL,
                    section_order INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for better query performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_papers_pdf_path 
                ON papers(pdf_path)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_text_blocks_paper_id 
                ON text_blocks(paper_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_text_blocks_page_number 
                ON text_blocks(paper_id, page_number)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sections_paper_id 
                ON sections(paper_id)
            """)
            
            conn.commit()
    
    def store_extraction_results(
        self,
        pdf_path: str,
        metadata: PaperMetadata,
        text_blocks: List[TextBlock]
    ) -> int:
        """Store complete extraction results in database.
        
        Args:
            pdf_path: Path to the PDF file
            metadata: Extracted paper metadata
            text_blocks: List of extracted text blocks
            
        Returns:
            paper_id: Database ID of the stored paper
            
        Raises:
            sqlite3.Error: If database operation fails
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if paper already exists
            cursor.execute("SELECT id FROM papers WHERE pdf_path = ?", (pdf_path,))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing paper
                paper_id = existing['id']
                cursor.execute("""
                    UPDATE papers 
                    SET title = ?, abstract = ?, paper_type = ?, 
                        difficulty = ?, math_heavy = ?, 
                        extraction_date = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    metadata.title,
                    metadata.abstract,
                    metadata.inference.paper_type,
                    metadata.inference.difficulty,
                    metadata.inference.math_heavy,
                    paper_id
                ))
                
                # Delete old text blocks and sections
                cursor.execute("DELETE FROM text_blocks WHERE paper_id = ?", (paper_id,))
                cursor.execute("DELETE FROM sections WHERE paper_id = ?", (paper_id,))
            else:
                # Insert new paper
                pdf_filename = Path(pdf_path).name
                cursor.execute("""
                    INSERT INTO papers 
                    (pdf_path, pdf_filename, title, abstract, paper_type, difficulty, math_heavy)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    pdf_path,
                    pdf_filename,
                    metadata.title,
                    metadata.abstract,
                    metadata.inference.paper_type,
                    metadata.inference.difficulty,
                    metadata.inference.math_heavy
                ))
                paper_id = cursor.lastrowid
            
            # Insert text blocks
            for block in text_blocks:
                metadata_json = json.dumps(block.metadata) if block.metadata else None
                cursor.execute("""
                    INSERT INTO text_blocks 
                    (paper_id, text, page_number, element_type, metadata_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    paper_id,
                    block.text,
                    block.page_number,
                    block.element_type,
                    metadata_json
                ))
            
            # Insert sections
            for idx, section in enumerate(metadata.sections, start=1):
                cursor.execute("""
                    INSERT INTO sections 
                    (paper_id, section_name, page_start, section_order)
                    VALUES (?, ?, ?, ?)
                """, (
                    paper_id,
                    section.original_name,
                    section.page_start,
                    idx
                ))
            
            conn.commit()
            return paper_id
    
    def get_paper_by_id(self, paper_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve paper metadata by ID.
        
        Args:
            paper_id: Database ID of the paper
            
        Returns:
            Dictionary containing paper information or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
    
    def get_paper_by_path(self, pdf_path: str) -> Optional[Dict[str, Any]]:
        """Retrieve paper metadata by PDF path.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary containing paper information or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM papers WHERE pdf_path = ?", (pdf_path,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
    
    def get_text_blocks(self, paper_id: int, page_number: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve text blocks for a paper.
        
        Args:
            paper_id: Database ID of the paper
            page_number: Optional page number to filter by
            
        Returns:
            List of text block dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if page_number is not None:
                cursor.execute("""
                    SELECT * FROM text_blocks 
                    WHERE paper_id = ? AND page_number = ?
                    ORDER BY id
                """, (paper_id, page_number))
            else:
                cursor.execute("""
                    SELECT * FROM text_blocks 
                    WHERE paper_id = ?
                    ORDER BY page_number, id
                """, (paper_id,))
            
            rows = cursor.fetchall()
            blocks = []
            for row in rows:
                block = dict(row)
                # Parse JSON metadata
                if block['metadata_json']:
                    block['metadata'] = json.loads(block['metadata_json'])
                else:
                    block['metadata'] = {}
                del block['metadata_json']
                blocks.append(block)
            
            return blocks
    
    def get_sections(self, paper_id: int) -> List[Dict[str, Any]]:
        """Retrieve sections for a paper.
        
        Args:
            paper_id: Database ID of the paper
            
        Returns:
            List of section dictionaries ordered by section_order
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sections 
                WHERE paper_id = ?
                ORDER BY section_order
            """, (paper_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_papers(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve all papers from database.
        
        Args:
            limit: Optional limit on number of papers to return
            
        Returns:
            List of paper dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if limit:
                cursor.execute("""
                    SELECT * FROM papers 
                    ORDER BY extraction_date DESC 
                    LIMIT ?
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT * FROM papers 
                    ORDER BY extraction_date DESC
                """)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def search_papers(
        self,
        query: str,
        search_in: List[str] = ['title', 'abstract']
    ) -> List[Dict[str, Any]]:
        """Search papers by text query.
        
        Args:
            query: Search query string
            search_in: List of fields to search in ('title', 'abstract', 'sections')
            
        Returns:
            List of matching paper dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if 'title' in search_in:
                conditions.append("title LIKE ?")
                params.append(f"%{query}%")
            
            if 'abstract' in search_in:
                conditions.append("abstract LIKE ?")
                params.append(f"%{query}%")
            
            where_clause = " OR ".join(conditions)
            
            cursor.execute(f"""
                SELECT * FROM papers 
                WHERE {where_clause}
                ORDER BY extraction_date DESC
            """, params)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_paper_statistics(self) -> Dict[str, Any]:
        """Get database statistics.
        
        Returns:
            Dictionary with statistics about stored papers
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Total papers
            cursor.execute("SELECT COUNT(*) as count FROM papers")
            total_papers = cursor.fetchone()['count']
            
            # Total text blocks
            cursor.execute("SELECT COUNT(*) as count FROM text_blocks")
            total_blocks = cursor.fetchone()['count']
            
            # Total sections
            cursor.execute("SELECT COUNT(*) as count FROM sections")
            total_sections = cursor.fetchone()['count']
            
            # Papers by type
            cursor.execute("""
                SELECT paper_type, COUNT(*) as count 
                FROM papers 
                GROUP BY paper_type
            """)
            papers_by_type = {row['paper_type']: row['count'] for row in cursor.fetchall()}
            
            # Papers by difficulty
            cursor.execute("""
                SELECT difficulty, COUNT(*) as count 
                FROM papers 
                GROUP BY difficulty
            """)
            papers_by_difficulty = {row['difficulty']: row['count'] for row in cursor.fetchall()}
            
            return {
                'total_papers': total_papers,
                'total_text_blocks': total_blocks,
                'total_sections': total_sections,
                'papers_by_type': papers_by_type,
                'papers_by_difficulty': papers_by_difficulty
            }
    
    def delete_paper(self, paper_id: int) -> bool:
        """Delete a paper and all its associated data.
        
        Args:
            paper_id: Database ID of the paper to delete
            
        Returns:
            True if paper was deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def reconstruct_metadata(self, paper_id: int) -> Optional[PaperMetadata]:
        """Reconstruct PaperMetadata object from database.
        
        Args:
            paper_id: Database ID of the paper
            
        Returns:
            PaperMetadata object or None if not found
        """
        paper = self.get_paper_by_id(paper_id)
        if not paper:
            return None
        
        sections_data = self.get_sections(paper_id)
        sections = [
            SectionMetadata(
                original_name=s['section_name'],
                page_start=s['page_start']
            )
            for s in sections_data
        ]
        
        inference = PaperInference(
            paper_type=paper['paper_type'],
            difficulty=paper['difficulty'],
            math_heavy=bool(paper['math_heavy'])
        )
        
        metadata = PaperMetadata(
            title=paper['title'],
            abstract=paper['abstract'],
            sections=sections,
            inference=inference
        )
        
        return metadata
    
    def reconstruct_text_blocks(self, paper_id: int) -> Optional[List[TextBlock]]:
        """Reconstruct TextBlock objects from database.
        
        Args:
            paper_id: Database ID of the paper
            
        Returns:
            List of TextBlock objects or None if not found
        """
        paper = self.get_paper_by_id(paper_id)
        if not paper:
            return None
        
        blocks_data = self.get_text_blocks(paper_id)
        text_blocks = [
            TextBlock(
                text=b['text'],
                page_number=b['page_number'],
                element_type=b['element_type'],
                metadata=b.get('metadata', {})
            )
            for b in blocks_data
        ]
        
        return text_blocks
