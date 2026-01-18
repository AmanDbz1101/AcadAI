"""
Main extraction interface.

This is the public API for metadata extraction.
"""

from typing import Optional
from .graph import MetadataExtractionGraph
from .models import PaperMetadata
from .database import QdrantFetcher
from .section_detection import SectionDetector
from .llm_inference import PaperInferenceEngine


def extract_metadata(
    document_id: str,
    collection_name: str = "research_papers_main",
    qdrant_url: Optional[str] = None,
    qdrant_api_key: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    save_to_file: bool = False,
    output_path: Optional[str] = None
) -> PaperMetadata:
    """
    Extract metadata for a research paper.
    
    This is the main entry point for metadata extraction.
    
    Args:
        document_id: Document identifier (usually filename)
        collection_name: Qdrant collection name
        qdrant_url: Qdrant server URL (optional)
        qdrant_api_key: Qdrant API key (optional)
        groq_api_key: Groq API key for LLM inference (optional)
        save_to_file: Whether to save output to JSON file
        output_path: Path for output JSON file
        
    Returns:
        Complete paper metadata
        
    Example:
        >>> metadata = extract_metadata("Gated Attention.pdf")
        >>> print(metadata.paper_title)
        >>> print(f"Sections: {len(metadata.sections)}")
        >>> print(f"Math heavy: {metadata.inference.math_heavy}")
    """
    # Initialize components
    fetcher = QdrantFetcher(
        collection_name=collection_name,
        url=qdrant_url,
        api_key=qdrant_api_key
    )
    
    detector = SectionDetector()
    
    inference_engine = PaperInferenceEngine(api_key=groq_api_key)
    
    # Create graph
    graph = MetadataExtractionGraph(
        fetcher=fetcher,
        detector=detector,
        inference_engine=inference_engine
    )
    
    # Extract metadata
    metadata = graph.extract(document_id)
    
    # Optionally save to file
    if save_to_file:
        output_path = output_path or f"{document_id}_metadata.json"
        with open(output_path, 'w') as f:
            f.write(metadata.model_dump_json())
        print(f"Metadata saved to {output_path}")
    
    return metadata


def list_available_documents(
    collection_name: str = "research_papers_main",
    qdrant_url: Optional[str] = None,
    qdrant_api_key: Optional[str] = None
) -> list[str]:
    """
    List all available documents in Qdrant collection.
    
    Args:
        collection_name: Qdrant collection name
        qdrant_url: Qdrant server URL (optional)
        qdrant_api_key: Qdrant API key (optional)
        
    Returns:
        List of document IDs
        
    Example:
        >>> docs = list_available_documents()
        >>> print(f"Found {len(docs)} documents")
        >>> for doc in docs:
        ...     print(f"  - {doc}")
    """
    fetcher = QdrantFetcher(
        collection_name=collection_name,
        url=qdrant_url,
        api_key=qdrant_api_key
    )
    
    return fetcher.list_documents()
