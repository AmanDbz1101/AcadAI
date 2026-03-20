"""
Section Content Query Module

Easy-to-use interface for extracting content from specific paper sections
(introduction, conclusion, methods, results, etc.)

Example usage::

    from backend.rag.retrieval.section_query import get_introduction, get_conclusion, get_all_sections
    
    # Get introduction from a paper
    intro = get_introduction(document_id="2f5cdbf0-49e0-46af-8bdc-d861443d92c7")
    print(intro['content'][:500])
    
    # Get conclusion
    conclusion = get_conclusion("2f5cdbf0-49e0-46af-8bdc-d861443d92c7")
    print(f"Conclusion pages: {conclusion['page_start']}-{conclusion['page_end']}")
    
    # Get multiple sections at once
    sections = get_all_sections(
        "2f5cdbf0-49e0-46af-8bdc-d861443d92c7",
        keywords={
            'introduction': ['introduction', 'intro'],
            'methods': ['method', 'methodology', 'approach'],
            'conclusion': ['conclusion', 'future work'],
        }
    )
    
    for name, section in sections.items():
        if section['found']:
            print(f"{name}: {section['content_length']} chars")
"""

import os
from typing import Optional, Dict, List, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def _get_engine():
    """Get SQLAlchemy engine for the research database."""
    database_url = (
        os.getenv("DATABASE_URL") or
        "postgresql+psycopg://postgres@localhost:5432/research_agent"
    )
    return create_engine(database_url, pool_pre_ping=True)


def get_all_documents() -> List[Dict[str, Any]]:
    """
    Get list of all documents in database.
    
    Returns:
        List of dicts with keys: id, filename, title, total_sections
    """
    engine = _get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT id, filename, title, total_sections FROM documents ORDER BY created_at DESC"
        ))
        return [
            {
                'id': str(row[0]),
                'filename': row[1],
                'title': row[2] or "N/A",
                'total_sections': row[3]
            }
            for row in result
        ]


def get_all_sections(
    document_id: str,
    keywords: Optional[Dict[str, List[str]]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Extract multiple sections from a paper.
    
    Args:
        document_id: UUID of the document
        keywords: Dict mapping section names to keyword lists
                 e.g., {'introduction': ['introduction', 'intro'],
                        'methods': ['method', 'methodology']}
                 If None, defaults to: introduction, abstract, methods, results, conclusion
    
    Returns:
        Dict mapping section names to extraction results with keys:
        - found (bool): Whether section was found
        - title (str): Section title
        - level (int): Heading level (1 = top-level)
        - numbering (str): Section number if present
        - page_start (int): Starting page
        - page_end (int): Ending page
        - content_length (int): Number of characters
        - content (str): Full text content
    """
    if keywords is None:
        keywords = {
            'abstract': ['abstract'],
            'introduction': ['introduction', 'intro', 'background'],
            'methods': ['method', 'methodology', 'approach'],
            'results': ['result', 'experiment', 'evaluation'],
            'conclusion': ['conclusion', 'concluding', 'future work'],
        }
    
    engine = _get_engine()
    results = {}
    
    with engine.connect() as conn:
        # Get all sections for the document
        all_sections_result = conn.execute(text(
            "SELECT id, title, level, numbering, page_start, page_end, reading_order "
            "FROM sections WHERE document_id = :doc_id ORDER BY reading_order"
        ),
        {'doc_id': document_id}
        )
        
        all_sections = [
            {
                'id': row[0],
                'title': row[1],
                'level': row[2],
                'numbering': row[3],
                'page_start': row[4],
                'page_end': row[5],
                'reading_order': row[6],
            }
            for row in all_sections_result
        ]
    
    # Find and extract each requested section
    for section_name, keyword_list in keywords.items():
        matching_section = None
        
        # Find first section matching any keyword
        for section in all_sections:
            title_lower = section['title'].lower()
            for keyword in keyword_list:
                if keyword.lower() in title_lower:
                    matching_section = section
                    break
            if matching_section:
                break
        
        if matching_section:
            # Get content for this section
            with engine.connect() as conn:
                content_result = conn.execute(text(
                    "SELECT content FROM text_blocks WHERE section_id = :sec_id ORDER BY reading_order"
                ),
                {'sec_id': matching_section['id']}
                )
                
                content_parts = [row[0] for row in content_result if row[0]]
                content = "\n\n".join(content_parts)
            
            results[section_name] = {
                'found': True,
                'title': matching_section['title'],
                'level': matching_section['level'],
                'numbering': matching_section['numbering'],
                'page_start': matching_section['page_start'],
                'page_end': matching_section['page_end'],
                'content_length': len(content),
                'content': content,
            }
        else:
            results[section_name] = {
                'found': False,
                'title': None,
                'level': None,
                'numbering': None,
                'page_start': None,
                'page_end': None,
                'content_length': 0,
                'content': None,
            }
    
    return results


def get_section(
    document_id: str,
    keywords: List[str]
) -> Optional[Dict[str, Any]]:
    """
    Extract a single section from a paper.
    
    Returns the first section matching any of the provided keywords.
    
    Args:
        document_id: UUID of the document
        keywords: List of keywords to match (case-insensitive substring match)
                 e.g., ['introduction', 'intro']
    
    Returns:
        Dict with keys: found, title, level, numbering, page_start, page_end, content_length, content
        Or None if section not found
    """
    results = get_all_sections(document_id, {'section': keywords})
    result = results['section']
    return result if result['found'] else None


def get_introduction(document_id: str) -> Dict[str, Any]:
    """Get introduction section from a paper."""
    return get_all_sections(
        document_id,
        {'introduction': ['introduction', 'intro', 'background']}
    )['introduction']


def get_abstract(document_id: str) -> Dict[str, Any]:
    """Get abstract section from a paper."""
    return get_all_sections(
        document_id,
        {'abstract': ['abstract']}
    )['abstract']


def get_conclusion(document_id: str) -> Dict[str, Any]:
    """Get conclusion section from a paper."""
    return get_all_sections(
        document_id,
        {'conclusion': ['conclusion', 'concluding', 'conclusions', 'future work']}
    )['conclusion']


def get_methods(document_id: str) -> Dict[str, Any]:
    """Get methods/methodology section from a paper."""
    return get_all_sections(
        document_id,
        {'methods': ['method', 'methodology', 'approach', 'proposed']}
    )['methods']


def get_results(document_id: str) -> Dict[str, Any]:
    """Get results/evaluation section from a paper."""
    return get_all_sections(
        document_id,
        {'results': ['result', 'experiment', 'evaluation', 'analysis']}
    )['results']


def print_section(section: Dict[str, Any], max_chars: Optional[int] = None) -> None:
    """
    Pretty-print a section with metadata.
    
    Args:
        section: Section dict from get_* functions
        max_chars: Max characters to display (default: full length)
    """
    if not section['found']:
        print(f"✗ Section not found")
        return
    
    print(f"\n{'=' * 80}")
    print(f"{section['title'].upper()}")
    print(f"{'=' * 80}")
    print(f"Level: {section['level']} | Pages: {section['page_start']}", end="")
    if section['page_end'] and section['page_end'] != section['page_start']:
        print(f" - {section['page_end']}", end="")
    print(f" | Length: {section['content_length']} chars")
    print(f"{'-' * 80}")
    
    content = section['content']
    if max_chars:
        content = content[:max_chars]
        if len(section['content']) > max_chars:
            content += "\n\n[... content truncated ...]"
    
    print(content)


if __name__ == "__main__":
    # Example usage
    import json
    
    print("Available documents:")
    docs = get_all_documents()
    for doc in docs:
        print(f"  ├─ {doc['filename']:30} (UUID: {doc['id']})")
    
    if docs:
        doc_id = docs[0]['id']
        print(f"\nExtracting sections from: {docs[0]['filename']}")
        
        sections = get_all_sections(doc_id)
        
        for name, section in sections.items():
            if section['found']:
                print(f"✓ {name:15} | {section['content_length']:6} chars | {section['title']}")
            else:
                print(f"✗ {name:15} | NOT FOUND")
