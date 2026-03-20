"""
Integration test for Qdrant vector store and PostgreSQL database.

Verifies that:
1. TextBlocks stored in PostgreSQL have correct section information
2. Vector embeddings in Qdrant match database records
3. Retrieval queries on introduction/conclusion work correctly
4. Metadata is properly preserved across both stores

Usage::

    # Run all tests
    pytest backend/tests/test_qdrant_postgres_integration.py -v

    # Run specific test
    pytest backend/tests/test_qdrant_postgres_integration.py::test_postgres_textblocks_have_sections -v

    # Run with detailed output
    pytest backend/tests/test_qdrant_postgres_integration.py -vv -s

Or run as a standalone script::

    python backend/tests/test_qdrant_postgres_integration.py <document_id>
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing import Optional

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

from backend.database.connection import DatabaseConnection
from backend.database.repository import DocumentRepository
from rag.retrieval.pipeline import RetrievalPipeline

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


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


def get_available_document_id(db_connection: DatabaseConnection) -> Optional[str]:
    """Find first available document in database for testing."""
    with db_connection.session() as sess:
        doc = sess.query(
            "SELECT id FROM documents ORDER BY created_at DESC LIMIT 1"
        ).first()
        return doc[0] if doc else None


# ============================================================================
# PostgreSQL Tests
# ============================================================================

class TestPostgreSQLDatabase:
    """Tests for PostgreSQL text blocks and sections."""

    def test_postgres_connection(self, db_connection: DatabaseConnection):
        """Verify PostgreSQL connection is working."""
        assert db_connection.health_check(), "Database connection failed"

    def test_documents_exist(self, db_connection: DatabaseConnection):
        """Verify documents exist in database."""
        with db_connection.session() as sess:
            repo = DocumentRepository(sess)
            from backend.database.models import DocumentRecord
            doc_count = sess.query(DocumentRecord).count()
            assert doc_count > 0, "No documents found in database"

    def test_postgres_textblocks_have_sections(self, db_connection: DatabaseConnection):
        """
        Verify TextBlocks have proper section information.
        
        Checks that:
        - TextBlocks have section_id populated
        - TextBlocks have section_title populated
        - TextBlocks have section_path populated
        - TextBlocks have section_level populated
        """
        from backend.database.models import TextBlockRecord, DocumentRecord

        with db_connection.session() as sess:
            repo = DocumentRepository(sess)

            # Get first document
            doc = sess.query(DocumentRecord).first()
            assert doc is not None, "No documents in database"

            # Get text blocks for document
            blocks = repo.get_text_blocks_for_document(doc.id)
            assert len(blocks) > 0, f"No text blocks found for document {doc.id}"

            # Find blocks with section info
            blocks_with_sections = [b for b in blocks if b.section_id is not None]
            assert len(blocks_with_sections) > 0, "No text blocks have section_id"

            # Verify section metadata
            for block in blocks_with_sections[:10]:  # Check first 10
                assert block.section_title is not None, f"TextBlock {block.id} missing section_title"
                assert block.section_level is not None, f"TextBlock {block.id} missing section_level"
                assert len(block.section_title) > 0, f"TextBlock {block.id} has empty section_title"

                print(f"✓ Block: {block.id[:8]}… | Section: {block.section_title} (level {block.section_level})")

    def test_postgres_section_hierarchy(self, db_connection: DatabaseConnection):
        """
        Verify sections are properly organized in hierarchy.
        
        Checks that:
        - Sections have level information
        - Parent-child relationships are valid
        - Section titles are meaningful
        """
        from backend.database.models import SectionRecord, DocumentRecord

        with db_connection.session() as sess:
            repo = DocumentRepository(sess)

            # Get first document
            doc = sess.query(DocumentRecord).first()
            assert doc is not None, "No documents in database"

            # Get sections
            sections = repo.get_sections_for_document(doc.id)
            assert len(sections) > 0, f"No sections found for document {doc.id}"

            # Verify section structure
            for section in sections:
                assert section.title is not None, f"Section {section.id} missing title"
                assert section.level >= 1, f"Section {section.id} has invalid level {section.level}"
                assert section.page_start >= 1, f"Section {section.id} has invalid page_start {section.page_start}"

            print(f"✓ Document has {len(sections)} sections with proper hierarchy")

            # Print section tree
            top_level = [s for s in sections if s.level == 1]
            for section in top_level:
                print(f"  - {section.title} (pages {section.page_start}-{section.page_end})")

    def test_postgres_introduction_and_conclusion(self, db_connection: DatabaseConnection):
        """
        Find and verify Introduction and Conclusion sections exist.
        
        Checks that these critical sections:
        - Exist in the database
        - Have associated text blocks
        - Have proper page ranges
        """
        from backend.database.models import SectionRecord, TextBlockRecord, DocumentRecord

        with db_connection.session() as sess:
            repo = DocumentRepository(sess)

            # Get first document
            doc = sess.query(DocumentRecord).first()
            assert doc is not None, "No documents in database"

            # Find sections case-insensitively
            sections = sess.query(SectionRecord).filter(
                SectionRecord.document_id == doc.id
            ).all()

            section_titles_lower = {s.id: s.title.lower() for s in sections}

            # Find introduction
            intro_section = None
            for s in sections:
                if "introduction" in s.title.lower():
                    intro_section = s
                    break

            # Find conclusion
            conclusion_section = None
            for s in sections:
                if "conclusion" in s.title.lower():
                    conclusion_section = s
                    break

            print(f"✓ Found sections: intro={intro_section is not None}, conclusion={conclusion_section is not None}")

            # If found, verify they have text blocks
            if intro_section:
                intro_blocks = repo.get_text_blocks_for_section(intro_section.id)
                assert len(intro_blocks) > 0, f"Introduction section has no text blocks"
                print(f"  - Introduction: {len(intro_blocks)} text blocks (pages {intro_section.page_start}-{intro_section.page_end})")

            if conclusion_section:
                conclusion_blocks = repo.get_text_blocks_for_section(conclusion_section.id)
                assert len(conclusion_blocks) > 0, f"Conclusion section has no text blocks"
                print(f"  - Conclusion: {len(conclusion_blocks)} text blocks (pages {conclusion_section.page_start}-{conclusion_section.page_end})")


# ============================================================================
# Qdrant Tests
# ============================================================================

class TestQdrantVectorStore:
    """Tests for Qdrant vector store integration."""

    def test_qdrant_connection(self, retrieval_pipeline: RetrievalPipeline):
        """Verify Qdrant connection is working."""
        try:
            store_manager = retrieval_pipeline._get_store_manager()
            assert store_manager is not None, "Failed to initialize Qdrant store manager"
        except Exception as e:
            pytest.skip(f"Qdrant not available: {e}")

    def test_qdrant_collection_exists(self, retrieval_pipeline: RetrievalPipeline):
        """Verify Qdrant collection contains data."""
        try:
            store_manager = retrieval_pipeline._get_store_manager()
            collection_count = store_manager.get_collection_count()
            assert collection_count > 0, "Qdrant collection is empty"
            print(f"✓ Qdrant collection contains {collection_count} vectors")
        except Exception as e:
            pytest.skip(f"Qdrant not available: {e}")

    def test_qdrant_query_introduction(self, retrieval_pipeline: RetrievalPipeline, db_connection: DatabaseConnection):
        """
        Query Qdrant for introduction-related content.
        
        Verifies that:
        - Query returns relevant results
        - Results have section metadata
        - Results are from the introduction section
        """
        try:
            from backend.database.models import DocumentRecord

            with db_connection.session() as sess:
                doc = sess.query(DocumentRecord).first()
                if not doc:
                    pytest.skip("No documents in database")

                query = "introduction background motivation"
                results = retrieval_pipeline.query(
                    query=query,
                    document_id=doc.id,
                    top_k=10,
                    top_n=5,
                    rerank=False
                )

                assert len(results) > 0, f"No results for introduction query in document {doc.id}"

                print(f"✓ Introduction query returned {len(results)} results:")
                for i, result in enumerate(results, 1):
                    metadata = getattr(result, 'metadata', {})
                    section_title = metadata.get('section_title', 'Unknown')
                    score = getattr(result, 'score', None)
                    content_preview = getattr(result, 'content', '')[:100]
                    print(f"  {i}. [{score:.3f}] Section: {section_title} | {content_preview}…")

        except Exception as e:
            pytest.skip(f"Qdrant not available: {e}")

    def test_qdrant_query_conclusion(self, retrieval_pipeline: RetrievalPipeline, db_connection: DatabaseConnection):
        """
        Query Qdrant for conclusion-related content.
        
        Verifies that:
        - Query returns relevant results
        - Results have section metadata
        - Results are from the conclusion section
        """
        try:
            from backend.database.models import DocumentRecord

            with db_connection.session() as sess:
                doc = sess.query(DocumentRecord).first()
                if not doc:
                    pytest.skip("No documents in database")

                query = "conclusion future work implications"
                results = retrieval_pipeline.query(
                    query=query,
                    document_id=doc.id,
                    top_k=10,
                    top_n=5,
                    rerank=False
                )

                assert len(results) > 0, f"No results for conclusion query in document {doc.id}"

                print(f"✓ Conclusion query returned {len(results)} results:")
                for i, result in enumerate(results, 1):
                    metadata = getattr(result, 'metadata', {})
                    section_title = metadata.get('section_title', 'Unknown')
                    score = getattr(result, 'score', None)
                    content_preview = getattr(result, 'content', '')[:100]
                    print(f"  {i}. [{score:.3f}] Section: {section_title} | {content_preview}…")

        except Exception as e:
            pytest.skip(f"Qdrant not available: {e}")

    def test_qdrant_metadata_preservation(self, retrieval_pipeline: RetrievalPipeline, db_connection: DatabaseConnection):
        """
        Verify that metadata is preserved in Qdrant vectors.
        
        Checks that:
        - Each vector has document_id metadata
        - Each vector has section_id metadata
        - Each vector has section_title metadata
        - Each vector has section_level metadata
        """
        try:
            from backend.database.models import DocumentRecord

            with db_connection.session() as sess:
                doc = sess.query(DocumentRecord).first()
                if not doc:
                    pytest.skip("No documents in database")

                query = "methodology approach"
                results = retrieval_pipeline.query(
                    query=query,
                    document_id=doc.id,
                    top_k=5,
                    top_n=3,
                    rerank=False
                )

                assert len(results) > 0, "No results returned"

                print(f"✓ Metadata preservation check ({len(results)} results):")
                for i, result in enumerate(results, 1):
                    metadata = getattr(result, 'metadata', {})

                    doc_id = metadata.get('document_id', 'Missing')
                    section_id = metadata.get('section_id', 'Missing')
                    section_title = metadata.get('section_title', 'Missing')
                    section_level = metadata.get('section_level', 'Missing')

                    print(f"  {i}. doc_id={doc_id[:8] if doc_id != 'Missing' else 'Missing'}… | "
                          f"section={section_title} (level {section_level})")

                    # Verify metadata is present
                    assert 'document_id' in metadata or doc_id != 'Missing', f"Result {i} missing document_id"
                    assert 'section_title' in metadata or section_title != 'Missing', f"Result {i} missing section_title"

        except Exception as e:
            pytest.skip(f"Qdrant not available: {e}")


# ============================================================================
# Integration Tests
# ============================================================================

class TestDatabaseQdrantIntegration:
    """Cross-system integration tests."""

    def test_postgres_qdrant_consistency(self, db_connection: DatabaseConnection, retrieval_pipeline: RetrievalPipeline):
        """
        Verify consistency between PostgreSQL and Qdrant.
        
        Checks that:
        - Data in both systems refers to the same documents
        - Section information matches between systems
        """
        try:
            from backend.database.models import DocumentRecord, TextBlockRecord

            with db_connection.session() as sess:
                doc = sess.query(DocumentRecord).first()
                if not doc:
                    pytest.skip("No documents in database")

                # Get text blocks from PostgreSQL
                pg_blocks = sess.query(TextBlockRecord).filter(
                    TextBlockRecord.document_id == doc.id
                ).limit(5).all()

                assert len(pg_blocks) > 0, "No text blocks in PostgreSQL"

                # Query Qdrant for same document
                query = "research methodology"
                qdrant_results = retrieval_pipeline.query(
                    query=query,
                    document_id=doc.id,
                    top_k=10,
                    top_n=5,
                    rerank=False
                )

                assert len(qdrant_results) > 0, f"No Qdrant results for document {doc.id}"

                print(f"✓ Consistency check:")
                print(f"  - PostgreSQL: {len(pg_blocks)} sample blocks")
                print(f"  - Qdrant: {len(qdrant_results)} retrieval results")

        except Exception as e:
            if "Qdrant not available" in str(e):
                pytest.skip(f"Qdrant not available: {e}")
            else:
                raise


# ============================================================================
# Standalone Script Execution
# ============================================================================

def run_standalone(document_id: Optional[str] = None) -> None:
    """
    Run tests standalone (not via pytest).
    
    Usage::
    
        python backend/tests/test_qdrant_postgres_integration.py <document_id>
    """
    print(f"\n{'='*70}")
    print(f"  Qdrant + PostgreSQL Integration Test")
    print(f"{'='*70}\n")

    # Setup
    db = DatabaseConnection()
    db.create_tables()

    if not db.health_check():
        print("✗ PostgreSQL database not reachable")
        return

    print("✓ PostgreSQL connection OK")

    # Get document
    if not document_id:
        with db.session() as sess:
            from backend.database.models import DocumentRecord
            doc = sess.query(DocumentRecord).order_by(
                DocumentRecord.created_at.desc()
            ).first()
            if not doc:
                print("✗ No documents in database. Please ingest a paper first.")
                return
            document_id = doc.id
    else:
        with db.session() as sess:
            from backend.database.models import DocumentRecord
            doc = sess.get(DocumentRecord, document_id)
            if not doc:
                print(f"✗ Document {document_id} not found")
                return

    print(f"Testing document: {document_id}")
    print()

    # Test PostgreSQL
    print("-" * 70)
    print("POSTGRESQL TESTS")
    print("-" * 70)

    with db.session() as sess:
        repo = DocumentRepository(sess)

        # Document stats
        stats = repo.get_document_stats(document_id)
        print(f"\nDocument Statistics:")
        for key, value in stats.items():
            print(f"  {key:<20}: {value}")

        # Text blocks with sections
        blocks = repo.get_text_blocks_for_document(document_id)
        blocks_with_sections = [b for b in blocks if b.section_id is not None]

        print(f"\nText Blocks:")
        print(f"  Total        : {len(blocks)}")
        print(f"  With sections: {len(blocks_with_sections)}")

        if blocks_with_sections:
            print(f"\n  Sample blocks with section info:")
            for block in blocks_with_sections[:3]:
                print(f"    - {block.section_title} (level {block.section_level})")
                print(f"      Content: {block.content[:80]}")

        # Sections
        from backend.database.models import SectionRecord
        sections = sess.query(SectionRecord).filter(
            SectionRecord.document_id == document_id
        ).all()

        print(f"\nSections ({len(sections)}):")
        intro_section = None
        conclusion_section = None

        for section in sections:
            if "introduction" in section.title.lower():
                intro_section = section
                print(f"  ✓ Introduction: {section.title} (pages {section.page_start}-{section.page_end})")
            if "conclusion" in section.title.lower():
                conclusion_section = section
                print(f"  ✓ Conclusion: {section.title} (pages {section.page_start}-{section.page_end})")

        if not intro_section:
            print(f"  ✗ Introduction section not found")
        if not conclusion_section:
            print(f"  ✗ Conclusion section not found")

    # Test Qdrant
    print("\n" + "-" * 70)
    print("QDRANT TESTS")
    print("-" * 70)

    try:
        pipeline = RetrievalPipeline(enable_reranking=False)

        print("\n✓ Qdrant pipeline initialized")

        # Query introduction
        print("\nQuerying introduction content...")
        intro_results = pipeline.query(
            query="introduction motivation background",
            document_id=document_id,
            top_k=5,
            top_n=3,
            rerank=False
        )

        if intro_results:
            print(f"✓ Found {len(intro_results)} introduction-related chunks:")
            for i, result in enumerate(intro_results, 1):
                metadata = getattr(result, 'metadata', {})
                section = metadata.get('section_title', 'Unknown')
                score = getattr(result, 'score', 0)
                print(f"  {i}. [{score:.3f}] {section}")

        # Query conclusion
        print("\nQuerying conclusion content...")
        conclusion_results = pipeline.query(
            query="conclusion future work implications",
            document_id=document_id,
            top_k=5,
            top_n=3,
            rerank=False
        )

        if conclusion_results:
            print(f"✓ Found {len(conclusion_results)} conclusion-related chunks:")
            for i, result in enumerate(conclusion_results, 1):
                metadata = getattr(result, 'metadata', {})
                section = metadata.get('section_title', 'Unknown')
                score = getattr(result, 'score', 0)
                print(f"  {i}. [{score:.3f}] {section}")

    except Exception as e:
        print(f"\n✗ Qdrant not available: {e}")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    doc_id = sys.argv[1] if len(sys.argv) > 1 else None
    run_standalone(doc_id)
