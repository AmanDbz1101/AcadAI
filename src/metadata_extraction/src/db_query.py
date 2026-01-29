"""
Convenient utility functions for querying the research paper database.

This module provides high-level functions for common database operations.
"""

from typing import Optional, List, Dict, Any
from src.metadata_extraction.src.database import DatabaseManager
from src.metadata_extraction.src.models import PaperMetadata
from src.metadata_extraction.src.text_extraction import TextBlock


def get_database(db_path: str = "research_papers.db") -> DatabaseManager:
    """Get database manager instance.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        DatabaseManager instance
    """
    return DatabaseManager(db_path)


def list_all_papers(db_path: str = "research_papers.db", limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """List all papers in database.
    
    Args:
        db_path: Path to SQLite database file
        limit: Optional limit on number of papers
        
    Returns:
        List of paper dictionaries
    """
    db = get_database(db_path)
    return db.get_all_papers(limit=limit)


def find_paper(pdf_path: str, db_path: str = "research_papers.db") -> Optional[Dict[str, Any]]:
    """Find a paper by PDF path.
    
    Args:
        pdf_path: Path to PDF file
        db_path: Path to SQLite database file
        
    Returns:
        Paper dictionary or None
    """
    db = get_database(db_path)
    return db.get_paper_by_path(pdf_path)


def search_papers(query: str, db_path: str = "research_papers.db") -> List[Dict[str, Any]]:
    """Search papers by text query.
    
    Args:
        query: Search query string
        db_path: Path to SQLite database file
        
    Returns:
        List of matching papers
    """
    db = get_database(db_path)
    return db.search_papers(query)


def get_paper_content(
    paper_id: int,
    db_path: str = "research_papers.db",
    include_text_blocks: bool = True
) -> Optional[Dict[str, Any]]:
    """Get complete paper content including metadata and text blocks.
    
    Args:
        paper_id: Database ID of the paper
        db_path: Path to SQLite database file
        include_text_blocks: Whether to include text blocks (default: True)
        
    Returns:
        Dictionary with paper data or None
    """
    db = get_database(db_path)
    
    paper = db.get_paper_by_id(paper_id)
    if not paper:
        return None
    
    result = {
        'paper': paper,
        'sections': db.get_sections(paper_id)
    }
    
    if include_text_blocks:
        result['text_blocks'] = db.get_text_blocks(paper_id)
    
    return result


def get_paper_text_by_page(
    paper_id: int,
    page_number: int,
    db_path: str = "research_papers.db"
) -> List[str]:
    """Get all text from a specific page.
    
    Args:
        paper_id: Database ID of the paper
        page_number: Page number to retrieve
        db_path: Path to SQLite database file
        
    Returns:
        List of text strings from the page
    """
    db = get_database(db_path)
    blocks = db.get_text_blocks(paper_id, page_number=page_number)
    return [block['text'] for block in blocks]


def reconstruct_paper_objects(
    paper_id: int,
    db_path: str = "research_papers.db"
) -> Optional[tuple[PaperMetadata, List[TextBlock]]]:
    """Reconstruct PaperMetadata and TextBlock objects from database.
    
    Args:
        paper_id: Database ID of the paper
        db_path: Path to SQLite database file
        
    Returns:
        Tuple of (PaperMetadata, List[TextBlock]) or None if not found
    """
    db = get_database(db_path)
    
    metadata = db.reconstruct_metadata(paper_id)
    text_blocks = db.reconstruct_text_blocks(paper_id)
    
    if metadata and text_blocks:
        return metadata, text_blocks
    return None


def show_database_stats(db_path: str = "research_papers.db") -> None:
    """Print database statistics.
    
    Args:
        db_path: Path to SQLite database file
    """
    db = get_database(db_path)
    stats = db.get_paper_statistics()
    
    print("=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)
    print(f"Total Papers: {stats['total_papers']}")
    print(f"Total Text Blocks: {stats['total_text_blocks']:,}")
    print(f"Total Sections: {stats['total_sections']}")
    print()
    
    if stats['papers_by_type']:
        print("Papers by Type:")
        for paper_type, count in stats['papers_by_type'].items():
            print(f"  {paper_type}: {count}")
        print()
    
    if stats['papers_by_difficulty']:
        print("Papers by Difficulty:")
        for difficulty, count in stats['papers_by_difficulty'].items():
            print(f"  {difficulty}: {count}")
        print()


def export_paper_to_text(
    paper_id: int,
    output_path: str,
    db_path: str = "research_papers.db"
) -> bool:
    """Export all paper text to a text file.
    
    Args:
        paper_id: Database ID of the paper
        output_path: Path to output text file
        db_path: Path to SQLite database file
        
    Returns:
        True if successful, False otherwise
    """
    db = get_database(db_path)
    
    paper = db.get_paper_by_id(paper_id)
    if not paper:
        return False
    
    text_blocks = db.get_text_blocks(paper_id)
    sections = db.get_sections(paper_id)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        # Write header
        f.write("=" * 80 + "\n")
        f.write(f"TITLE: {paper['title']}\n")
        f.write("=" * 80 + "\n\n")
        
        # Write abstract
        f.write("ABSTRACT\n")
        f.write("-" * 80 + "\n")
        f.write(paper['abstract'] + "\n\n")
        
        # Write sections
        f.write("SECTIONS\n")
        f.write("-" * 80 + "\n")
        for section in sections:
            f.write(f"- {section['section_name']} (Page {section['page_start']})\n")
        f.write("\n")
        
        # Write metadata
        f.write("METADATA\n")
        f.write("-" * 80 + "\n")
        f.write(f"Type: {paper['paper_type']}\n")
        f.write(f"Difficulty: {paper['difficulty']}\n")
        f.write(f"Math Heavy: {'Yes' if paper['math_heavy'] else 'No'}\n")
        f.write(f"Extraction Date: {paper['extraction_date']}\n\n")
        
        # Write full text
        f.write("FULL TEXT\n")
        f.write("=" * 80 + "\n\n")
        
        current_page = None
        for block in text_blocks:
            if block['page_number'] != current_page:
                current_page = block['page_number']
                f.write(f"\n--- Page {current_page} ---\n\n")
            
            f.write(block['text'] + "\n\n")
    
    return True


def delete_paper_from_db(paper_id: int, db_path: str = "research_papers.db") -> bool:
    """Delete a paper from the database.
    
    Args:
        paper_id: Database ID of the paper
        db_path: Path to SQLite database file
        
    Returns:
        True if deleted, False if not found
    """
    db = get_database(db_path)
    return db.delete_paper(paper_id)


# Example usage and testing
if __name__ == "__main__":
    # Show statistics
    show_database_stats()
    
    # List all papers
    print("\nAll Papers:")
    papers = list_all_papers(limit=10)
    for paper in papers:
        print(f"  [{paper['id']}] {paper['title']}")
        print(f"      Type: {paper['paper_type']}, Difficulty: {paper['difficulty']}")
