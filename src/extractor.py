"""
Research Paper Metadata Extractor - Main Entry Point

This module provides the main function to extract metadata from research papers.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from src.models import PaperMetadata
from src.graph import MetadataExtractionGraph

# Load environment variables from .env file
load_dotenv()


def extract_paper_metadata(pdf_path: str) -> PaperMetadata:
    """Extract structured metadata from a research paper PDF.
    
    This is the main entry point for the metadata extraction pipeline.
    It orchestrates all extraction steps using LangGraph.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        PaperMetadata object containing:
            - title: Paper title
            - abstract: Paper abstract
            - sections: List of detected sections with normalized names
            - inference: LLM-inferred paper properties
            
    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If Groq API key is not provided
        Exception: For other extraction errors
        
    Example:
        >>> metadata = extract_paper_metadata("paper.pdf")
        >>> print(metadata.title)
        >>> print(metadata.inference.paper_type)
        >>> for section in metadata.sections:
        >>>     print(f"{section.original_name} -> {section.normalized_name}")
    """
    # Validate PDF path
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    if not pdf_file.suffix.lower() == '.pdf':
        raise ValueError(f"File must be a PDF: {pdf_path}")
    
    # Validate API key is set
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError(
            "Groq API key not found. Make sure GROQ_API_KEY is set in your .env file."
        )
    
    # Create extraction graph
    graph = MetadataExtractionGraph()
    
    # Run extraction
    metadata = graph.extract(str(pdf_file.absolute()))
    
    return metadata


def extract_and_display(pdf_path: str) -> None:
    """Extract metadata and display results in a readable format.
    
    Convenience function for quick inspection of extraction results.
    
    Args:
        pdf_path: Path to the PDF file
    """
    metadata = extract_paper_metadata(pdf_path)
    
    print("=" * 80)
    print("RESEARCH PAPER METADATA")
    print("=" * 80)
    print()
    
    print(f"Title: {metadata.title}")
    print()
    
    print("Abstract:")
    print(metadata.abstract[:500] + "..." if len(metadata.abstract) > 500 else metadata.abstract)
    print()
    
    print("Sections:")
    for i, section in enumerate(metadata.sections, 1):
        normalized = section.normalized_name or "None"
        print(f"  {i}. {section.original_name}")
        print(f"     → Normalized: {normalized}")
        print(f"     → Page: {section.page_start}")
    print()
    
    print("Paper Analysis:")
    print(f"  Type: {metadata.inference.paper_type}")
    print(f"  Difficulty: {metadata.inference.difficulty}")
    print(f"  Math-Heavy: {metadata.inference.math_heavy}")
    print()
    print("=" * 80)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m src.extractor <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    extract_and_display(pdf_path)
