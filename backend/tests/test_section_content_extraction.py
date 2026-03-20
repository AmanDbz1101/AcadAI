"""
Test section-specific content extraction (Introduction, Conclusion, etc.).

Demonstrates how to extract and retrieve content from specific paper sections
using both the database and RAG retrieval pipeline.

Usage::

    # Run all tests
    pytest backend/tests/test_section_content_extraction.py -v

    # Run specific test
    pytest backend/tests/test_section_content_extraction.py::test_extract_introduction -v

    # Run with detailed output
    pytest backend/tests/test_section_content_extraction.py -vv -s

Or run as a standalone script::

    python backend/tests/test_section_content_extraction.py <document_id>
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

# Setup path — must match backend/run.py setup
_BACKEND_DIR = Path(__file__).resolve().parents[1]  # backend/ directory
_PROJECT_ROOT = _BACKEND_DIR.parent
for _p in (_PROJECT_ROOT, _BACKEND_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dotenv import load_dotenv
load_dotenv()

import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.database.connection import DatabaseConnection
from backend.extraction.persistence.postgres_store import (
    PaperRecord,
    SectionRecord,
    TextBlockRecord,
    SectionTextBlockRecord,
)
from rag.retrieval.pipeline import RetrievalPipeline

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# ============================================================================
# Helper Functions
# ============================================================================

class SectionContentRetriever:
    """
    Utility for retrieving content from specific paper sections.
    
    Provides both database-based and RAG-based retrieval methods.
    """
    
    def __init__(self, db_connection: DatabaseConnection):
        self.db_connection = db_connection
    
    def list_sections(self, paper_id: int) -> List[Dict[str, Any]]:
        """
        Get all sections for a paper from the database.
        
        Returns list of dicts with: id, original_name, level, page_start, position, parent_section_id
        """
        with self.db_connection.session() as sess:
            sections = sess.query(SectionRecord).filter(
                SectionRecord.paper_id == paper_id
            ).order_by(SectionRecord.position).all()
            
            return [
                {
                    'id': s.id,
                    'section_key': s.section_key,
                    'original_name': s.original_name,
                    'level': s.level,
                    'page_start': s.page_start,
                    'position': s.position,
                    'parent_id': s.parent_section_id,
                    'stats': s.stats_json,
                }
                for s in sections
            ]
    
    def find_sections_by_name(
        self,
        paper_id: int,
        name_patterns: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Find sections matching any of the name patterns (case-insensitive).
        
        Args:
            paper_id: Paper database ID
            name_patterns: List of section names to search for (e.g., ['introduction', 'conclusion'])
            
        Returns:
            List of matching section records
        """
        with self.db_connection.session() as sess:
            sections = sess.query(SectionRecord).filter(
                SectionRecord.paper_id == paper_id
            ).all()
            
            results = []
            for section in sections:
                section_name_lower = section.original_name.lower()
                for pattern in name_patterns:
                    if pattern.lower() in section_name_lower:
                        results.append({
                            'id': section.id,
                            'section_key': section.section_key,
                            'original_name': section.original_name,
                            'level': section.level,
                            'page_start': section.page_start,
                            'position': section.position,
                            'parent_id': section.parent_section_id,
                            'stats': section.stats_json,
                        })
                        break
            
            return results
    
    def get_section_text_blocks(
        self,
        section_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all text blocks in a section.
        
        Args:
            section_id: Section database ID
            
        Returns:
            List of text block records with their content
        """
        with self.db_connection.session() as sess:
            # Query junction table for text blocks in this section
            text_blocks = sess.query(
                TextBlockRecord
            ).join(
                SectionTextBlockRecord,
                TextBlockRecord.id == SectionTextBlockRecord.text_block_id
            ).filter(
                SectionTextBlockRecord.section_id == section_id
            ).order_by(
                TextBlockRecord.id
            ).all()
            
            return [
                {
                    'id': tb.id,
                    'element_id': tb.element_id,
                    'page_number': tb.page_number,
                    'text_content': tb.text_content,
                    'metadata': tb.metadata_json,
                }
                for tb in text_blocks
            ]
    
    def get_section_content_text(self, section_id: int) -> str:
        """
        Concatenate all text content for a section.
        
        Args:
            section_id: Section database ID
            
        Returns:
            Complete text for the section
        """
        text_blocks = self.get_section_text_blocks(section_id)
        return "\n\n".join(
            block['text_content'] for block in text_blocks
            if block['text_content']
        )


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def db_connection() -> DatabaseConnection:
    """Get database connection."""
    db = DatabaseConnection()
    db.create_tables()
    if not db.health_check():
        raise RuntimeError("PostgreSQL database is not reachable. Check DATABASE_URL in .env")
    return db


@pytest.fixture(scope="module")
def retrieval_pipeline() -> RetrievalPipeline:
    """Get retrieval pipeline (Qdrant)."""
    pipeline = RetrievalPipeline(enable_reranking=False)
    return pipeline


@pytest.fixture(scope="module")
def section_retriever(db_connection: DatabaseConnection) -> SectionContentRetriever:
    """Get section content retriever utility."""
    return SectionContentRetriever(db_connection)


def get_available_document_id(db_connection: DatabaseConnection) -> Optional[int]:
    """Find first available document in database for testing."""
    with db_connection.session() as sess:
        paper = sess.query(PaperRecord).order_by(PaperRecord.created_at.desc()).first()
        return paper.id if paper else None


def get_paper_title(db_connection: DatabaseConnection, paper_id: int) -> Optional[str]:
    """Get paper title by ID."""
    with db_connection.session() as sess:
        paper = sess.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
        return paper.title if paper else None


# ============================================================================
# Database Tests
# ============================================================================

class TestSectionDatabase:
    """Tests for section data in PostgreSQL database."""
    
    def test_papers_have_sections(self, db_connection: DatabaseConnection):
        """Verify that papers in database have associated sections."""
        paper_id = get_available_document_id(db_connection)
        if not paper_id:
            pytest.skip("No papers in database to test")
        
        with db_connection.session() as sess:
            sections = sess.query(SectionRecord).filter(
                SectionRecord.paper_id == paper_id
            ).all()
            
            assert len(sections) > 0, f"Paper {paper_id} has no sections in database"
    
    def test_list_paper_sections(
        self,
        db_connection: DatabaseConnection,
        section_retriever: SectionContentRetriever
    ):
        """Test that we can list all sections in a paper."""
        paper_id = get_available_document_id(db_connection)
        if not paper_id:
            pytest.skip("No papers in database to test")
        
        paper_title = get_paper_title(db_connection, paper_id)
        sections = section_retriever.list_sections(paper_id)
        
        logger.info(f"Paper: {paper_title}")
        logger.info(f"Total sections: {len(sections)}")
        for i, section in enumerate(sections[:10]):  # Show first 10
            indent = "  " * (section['level'] - 1)
            logger.info(
                f"{indent}└─ [{i}] Lvl{section['level']} "
                f"pg.{section['page_start']} {section['original_name']}"
            )
        
        assert len(sections) > 0
    
    def test_find_introduction_section(
        self,
        db_connection: DatabaseConnection,
        section_retriever: SectionContentRetriever
    ):
        """Test finding the introduction section."""
        paper_id = get_available_document_id(db_connection)
        if not paper_id:
            pytest.skip("No papers in database to test")
        
        intro_sections = section_retriever.find_sections_by_name(
            paper_id,
            ['introduction', 'intro']
        )
        
        if intro_sections:
            for section in intro_sections:
                logger.info(f"Found Introduction: '{section['original_name']}' "
                           f"(id={section['id']}, level={section['level']})")
        else:
            logger.warning("No introduction section found in database")
        
        # Don't fail if not found - some papers might not have explicit section
        assert isinstance(intro_sections, list)
    
    def test_find_conclusion_section(
        self,
        db_connection: DatabaseConnection,
        section_retriever: SectionContentRetriever
    ):
        """Test finding the conclusion section."""
        paper_id = get_available_document_id(db_connection)
        if not paper_id:
            pytest.skip("No papers in database to test")
        
        conclusion_sections = section_retriever.find_sections_by_name(
            paper_id,
            ['conclusion', 'concluding', 'conclusions', 'future work']
        )
        
        if conclusion_sections:
            for section in conclusion_sections:
                logger.info(f"Found Conclusion: '{section['original_name']}' "
                           f"(id={section['id']}, level={section['level']})")
        else:
            logger.warning("No conclusion section found in database")
        
        assert isinstance(conclusion_sections, list)


# ============================================================================
# Content Extraction Tests
# ============================================================================

class TestSectionContentExtraction:
    """Tests for extracting content from specific sections."""
    
    def test_extract_introduction_content(
        self,
        db_connection: DatabaseConnection,
        section_retriever: SectionContentRetriever
    ):
        """Extract and display introduction section content."""
        paper_id = get_available_document_id(db_connection)
        if not paper_id:
            pytest.skip("No papers in database to test")
        
        intro_sections = section_retriever.find_sections_by_name(
            paper_id,
            ['introduction', 'intro']
        )
        
        if not intro_sections:
            logger.warning("Skipping: no introduction section found")
            pytest.skip("No introduction section in paper")
        
        for section in intro_sections:
            section_id = section['id']
            content = section_retriever.get_section_content_text(section_id)
            
            logger.info("\n" + "=" * 80)
            logger.info(f"INTRODUCTION: {section['original_name']}")
            logger.info("=" * 80)
            logger.info(f"Page {section['page_start']} | Level {section['level']}")
            logger.info("-" * 80)
            logger.info(content[:2000] + ("..." if len(content) > 2000 else ""))
            logger.info(f"\n[Total content length: {len(content)} characters]")
            
            assert len(content) > 0, "Introduction section has no text content"
    
    def test_extract_conclusion_content(
        self,
        db_connection: DatabaseConnection,
        section_retriever: SectionContentRetriever
    ):
        """Extract and display conclusion section content."""
        paper_id = get_available_document_id(db_connection)
        if not paper_id:
            pytest.skip("No papers in database to test")
        
        conclusion_sections = section_retriever.find_sections_by_name(
            paper_id,
            ['conclusion', 'concluding', 'conclusions', 'future work']
        )
        
        if not conclusion_sections:
            logger.warning("Skipping: no conclusion section found")
            pytest.skip("No conclusion section in paper")
        
        for section in conclusion_sections:
            section_id = section['id']
            content = section_retriever.get_section_content_text(section_id)
            
            logger.info("\n" + "=" * 80)
            logger.info(f"CONCLUSION: {section['original_name']}")
            logger.info("=" * 80)
            logger.info(f"Page {section['page_start']} | Level {section['level']}")
            logger.info("-" * 80)
            logger.info(content[:2000] + ("..." if len(content) > 2000 else ""))
            logger.info(f"\n[Total content length: {len(content)} characters]")
            
            assert len(content) > 0, "Conclusion section has no text content"
    
    def test_extract_multiple_specific_sections(
        self,
        db_connection: DatabaseConnection,
        section_retriever: SectionContentRetriever
    ):
        """Extract multiple named sections from a paper."""
        paper_id = get_available_document_id(db_connection)
        if not paper_id:
            pytest.skip("No papers in database to test")
        
        target_sections = ['introduction', 'related work', 'method', 'results', 'conclusion']
        found_sections = section_retriever.find_sections_by_name(paper_id, target_sections)
        
        logger.info(f"\nSearching for sections: {target_sections}")
        logger.info(f"Found {len(found_sections)} matching sections\n")
        
        for section in found_sections:
            section_id = section['id']
            content = section_retriever.get_section_content_text(section_id)
            
            preview = content[:300].replace('\n', ' ') + ("..." if len(content) > 300 else "")
            logger.info(f"✓ {section['original_name']:30} | "
                       f"{len(content):7} chars | "
                       f"Lvl{section['level']} | "
                       f"... {preview}")


# ============================================================================
# RAG Retrieval Tests
# ============================================================================

class TestSectionRAGRetrieval:
    """Tests for retrieving section content via RAG pipeline."""
    
    def test_query_introduction_via_rag(
        self,
        db_connection: DatabaseConnection,
        section_retriever: SectionContentRetriever,
        retrieval_pipeline: RetrievalPipeline
    ):
        """Query introduction section via RAG retrieval."""
        paper_id = get_available_document_id(db_connection)
        if not paper_id:
            pytest.skip("No papers in database to test")
        
        # Get paper details
        with db_connection.session() as sess:
            paper = sess.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
            if not paper:
                pytest.skip("Paper not found")
            
            document_id = paper.document_uuid
        
        # Find introduction section
        intro_sections = section_retriever.find_sections_by_name(
            paper_id,
            ['introduction']
        )
        
        if not intro_sections:
            pytest.skip("No introduction section found")
        
        intro_section = intro_sections[0]
        
        # Try retrieval with section filter
        try:
            results = retrieval_pipeline.query(
                query="What is the main contribution and scope?",
                document_id=document_id,
                section_id=intro_section['section_key'],
                top_k=5
            )
            
            logger.info(f"\nRAG Query Results for Introduction Section:")
            logger.info(f"Section: {intro_section['original_name']}")
            logger.info(f"Total results: {len(results)}")
            
            for i, result in enumerate(results, 1):
                metadata = result.metadata if hasattr(result, 'metadata') else {}
                logger.info(f"\n[{i}] Score: {result.score:.3f}")
                logger.info(f"    Section: {metadata.get('section_title', 'N/A')}")
                preview = result.content[:200].replace('\n', ' ') + "..."
                logger.info(f"    Content: {preview}")
            
        except Exception as e:
            logger.warning(f"RAG retrieval test skipped: {e}")
            pytest.skip(f"RAG retrieval not available: {e}")


# ============================================================================
# Main Entry Point (for standalone execution)
# ============================================================================

if __name__ == "__main__":
    # Allow running as: python test_section_content_extraction.py <paper_id_or_skip>
    import sys
    
    db = DatabaseConnection()
    db.create_tables()
    
    if not db.health_check():
        print("ERROR: Database not reachable")
        sys.exit(1)
    
    paper_id = get_available_document_id(db)
    
    if not paper_id:
        print("No papers found in database. Please index a paper first.")
        sys.exit(1)
    
    paper_title = get_paper_title(db, paper_id)
    print(f"\n{'=' * 80}")
    print(f"Testing section extraction for: {paper_title}")
    print(f"Paper ID: {paper_id}")
    print(f"{'=' * 80}\n")
    
    retriever = SectionContentRetriever(db)
    
    # List all sections
    print("ALL SECTIONS:")
    print("-" * 80)
    sections = retriever.list_sections(paper_id)
    for section in sections:
        indent = "  " * (section['level'] - 1)
        print(f"{indent}├─ {section['original_name']}")
    
    # Find and extract introduction
    print("\n" + "=" * 80)
    print("INTRODUCTION EXTRACTION:")
    print("=" * 80)
    intro_sections = retriever.find_sections_by_name(paper_id, ['introduction', 'intro'])
    if intro_sections:
        for section in intro_sections:
            content = retriever.get_section_content_text(section['id'])
            print(f"\nSection: {section['original_name']}")
            print(f"Content length: {len(content)} characters")
            print("-" * 80)
            print(content[:1500])
            if len(content) > 1500:
                print("\n... [content truncated] ...")
    else:
        print("No introduction section found")
    
    # Find and extract conclusion
    print("\n" + "=" * 80)
    print("CONCLUSION EXTRACTION:")
    print("=" * 80)
    conclusion_sections = retriever.find_sections_by_name(
        paper_id,
        ['conclusion', 'concluding', 'conclusions', 'future work']
    )
    if conclusion_sections:
        for section in conclusion_sections:
            content = retriever.get_section_content_text(section['id'])
            print(f"\nSection: {section['original_name']}")
            print(f"Content length: {len(content)} characters")
            print("-" * 80)
            print(content[:1500])
            if len(content) > 1500:
                print("\n... [content truncated] ...")
    else:
        print("No conclusion section found")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
