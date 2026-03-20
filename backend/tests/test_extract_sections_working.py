"""
Extract introduction and conclusion sections from papers in the actual database schema.

This test works with the existing database structure that has:
- documents table (UUIDs)
- sections table (with title, level, page_start, etc.)
- text_blocks table (with section_id mapping)

Usage::

    pytest backend/tests/test_extract_sections_working.py -v

Or standalone::

    python backend/tests/test_extract_sections_working.py
"""

import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND_DIR.parent
for _p in (_PROJECT_ROOT, _BACKEND_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dotenv import load_dotenv
load_dotenv()

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SectionExtractor:
    """Extract content from specific sections in papers using the actual database schema."""
    
    def __init__(self, database_url: Optional[str] = None):
        if not database_url:
            database_url = (
                os.getenv("DATABASE_URL") or 
                "postgresql+psycopg://postgres@localhost:5432/research_agent"
            )
        
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
    
    def get_documents(self) -> List[Dict[str, Any]]:
        """Get all documents in the database."""
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT id, filename, title, total_sections FROM documents ORDER BY created_at DESC"
            ))
            return [
                {
                    'id': row[0],
                    'filename': row[1],
                    'title': row[2] or "N/A",
                    'total_sections': row[3]
                }
                for row in result
            ]
    
    def get_sections_for_document(self, document_id: str) -> List[Dict[str, Any]]:
        """Get all sections for a document."""
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT id, title, level, numbering, page_start, page_end, parent_id, reading_order "
                "FROM sections WHERE document_id = :doc_id ORDER BY reading_order"
            ),
            {'doc_id': document_id}
            )
            return [
                {
                    'id': row[0],
                    'title': row[1],
                    'level': row[2],
                    'numbering': row[3],
                    'page_start': row[4],
                    'page_end': row[5],
                    'parent_id': row[6],
                    'reading_order': row[7],
                }
                for row in result
            ]
    
    def find_sections_by_name(
        self,
        document_id: str,
        keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """Find sections matching any keyword (case-insensitive)."""
        all_sections = self.get_sections_for_document(document_id)
        
        results = []
        for section in all_sections:
            title_lower = section['title'].lower()
            for keyword in keywords:
                if keyword.lower() in title_lower:
                    results.append(section)
                    break
        
        return results
    
    def get_section_content(self, section_id: str) -> str:
        """Get all text content for a section."""
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT content FROM text_blocks WHERE section_id = :sec_id ORDER BY reading_order"
            ),
            {'sec_id': section_id}
            )
            
            content_parts = [row[0] for row in result if row[0]]
            return "\n\n".join(content_parts)
    
    def extract_sections_dict(
        self,
        document_id: str,
        section_keywords: Dict[str, List[str]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Extract multiple sections by category.
        
        Args:
            document_id: UUID of the document
            section_keywords: Dict mapping section names to keyword lists
                e.g., {'introduction': ['introduction', 'intro'], ...}
        
        Returns:
            Dict mapping section name to extraction result
        """
        results = {}
        
        for section_name, keywords in section_keywords.items():
            sections = self.find_sections_by_name(document_id, keywords)
            
            if sections:
                # Take the first matching section
                section = sections[0]
                content = self.get_section_content(section['id'])
                
                results[section_name] = {
                    'found': True,
                    'title': section['title'],
                    'level': section['level'],
                    'numbering': section['numbering'],
                    'page_start': section['page_start'],
                    'page_end': section['page_end'],
                    'content_length': len(content),
                    'content': content,
                }
            else:
                results[section_name] = {
                    'found': False,
                    'title': None,
                    'content': None,
                    'content_length': 0,
                }
        
        return results


def main():
    """Main test execution."""
    
    print("\n" + "=" * 100)
    print("RESEARCH PAPER SECTION EXTRACTION TEST")
    print("=" * 100)
    
    extractor = SectionExtractor()
    
    # Get available documents
    documents = extractor.get_documents()
    
    if not documents:
        print("\n✗ No documents found in database")
        return 1
    
    print(f"\n✓ Found {len(documents)} document(s) in database\n")
    
    for i, doc in enumerate(documents, 1):
        print(f"[{i}] {doc['filename']}")
        print(f"    Title: {doc['title']}")
        print(f"    Total sections: {doc['total_sections']}")
        print()
    
    # Extract sections from the first document
    doc_id = documents[0]['id']
    doc_filename = documents[0]['filename']
    
    print("=" * 100)
    print(f"SECTION EXTRACTION: {doc_filename}")
    print("=" * 100)
    
    # Define sections to extract
    target_sections = {
        'introduction': ['introduction', 'intro', 'background'],
        'abstract': ['abstract'],
        'motivation': ['motivation', 'problem statement'],
        'methods': ['method', 'methodology', 'approach', 'proposed'],
        'results': ['result', 'experiment', 'evaluation'],
        'conclusion': ['conclusion', 'concluding', 'conclusions', 'future work', 'discussion'],
        'references': ['reference', 'bibliography'],
    }
    
    # Extract sections
    print(f"\nExtracting sections from document: {doc_id}\n")
    extractions = extractor.extract_sections_dict(doc_id, target_sections)
    
    # Display results
    print("\n" + "-" * 100)
    print("EXTRACTION SUMMARY")
    print("-" * 100)
    
    for section_name, result in extractions.items():
        if result['found']:
            print(f"\n✓ {section_name.upper()}")
            print(f"  ├─ Title: {result['title']}")
            if result['numbering']:
                print(f"  ├─ Number: {result['numbering']}")
            print(f"  ├─ Level: {result['level']}")
            if result['page_start']:
                print(f"  ├─ Pages: {result['page_start']}", end="")
                if result['page_end'] and result['page_end'] != result['page_start']:
                    print(f" - {result['page_end']}", end="")
                print()
            print(f"  └─ Content length: {result['content_length']} characters")
        else:
            print(f"\n✗ {section_name.upper()} - NOT FOUND")
    
    # Show detailed content for introduction and conclusion
    print("\n" + "=" * 100)
    print("DETAILED EXTRACTION")
    print("=" * 100)
    
    for section_name in ['introduction', 'conclusion']:
        result = extractions[section_name]
        if result['found']:
            print(f"\n{section_name.upper()}: {result['title']}")
            print("-" * 100)
            print(f"Pages: {result['page_start']}", end="")
            if result['page_end'] and result['page_end'] != result['page_start']:
                print(f" - {result['page_end']}", end="")
            print(f" | Length: {result['content_length']} characters")
            print("-" * 100)
            
            # Show first 1500 characters
            preview = result['content'][:1500]
            print(preview)
            
            if len(result['content']) > 1500:
                print("\n[... content truncated for display ...]")
            
            print()
        else:
            print(f"\n{section_name.upper()}: NOT FOUND IN DATABASE")
    
    print("=" * 100)
    print("✓ TEST COMPLETE")
    print("=" * 100)
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
