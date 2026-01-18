"""
Qdrant data fetching layer.

This module handles ONLY fetching data from Qdrant.
NO embeddings, NO ingestion, NO vector search.
"""

import os
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient

from .models import QdrantPoint, DocumentGroup


class QdrantFetcher:
    """Fetches raw data from Qdrant collection."""
    
    def __init__(
        self,
        collection_name: str = "research_papers_main",
        url: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        """
        Initialize Qdrant client.
        
        Args:
            collection_name: Name of the Qdrant collection
            url: Qdrant server URL (defaults to env QDRANT_URL)
            api_key: Qdrant API key (defaults to env QDRANT_API_KEY)
        """
        self.collection_name = collection_name
        
        # Use environment variables if not provided
        self.url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        
        # Initialize client
        if self.api_key:
            self.client = QdrantClient(url=self.url, api_key=self.api_key)
        else:
            self.client = QdrantClient(url=self.url)
    
    def fetch_all_points(self, limit: int = 100) -> List[QdrantPoint]:
        """
        Fetch all points from the collection using scroll.
        
        Args:
            limit: Number of points per scroll request
            
        Returns:
            List of all points as QdrantPoint objects
        """
        all_points = []
        offset = None
        
        while True:
            result = self.client.scroll(
                collection_name=self.collection_name,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False  # We don't need vectors
            )
            
            points, next_offset = result
            
            # Convert to QdrantPoint objects
            for point in points:
                try:
                    # Extract metadata from payload
                    payload = point.payload or {}
                    metadata = payload.get('metadata', {})
                    
                    qdrant_point = QdrantPoint(
                        id=str(point.id),
                        page_number=metadata.get('page_number', 1),
                        category=metadata.get('category', 'Unknown'),
                        page_content=payload.get('page_content', ''),
                        element_id=metadata.get('element_id'),
                        parent_id=metadata.get('parent_id'),
                        coordinates=metadata.get('coordinates'),
                        metadata=metadata
                    )
                    all_points.append(qdrant_point)
                except Exception as e:
                    # Log but continue
                    print(f"Warning: Failed to parse point {point.id}: {e}")
                    continue
            
            if next_offset is None:
                break
            offset = next_offset
        
        return all_points
    
    def group_by_document(self, points: List[QdrantPoint]) -> Dict[str, DocumentGroup]:
        """
        Group points by document_id.
        
        Args:
            points: List of QdrantPoint objects
            
        Returns:
            Dictionary mapping document_id to DocumentGroup
        """
        groups: Dict[str, List[QdrantPoint]] = {}
        
        for point in points:
            # Extract document_id from metadata or filename
            doc_id = point.metadata.get('filename', 'unknown') if point.metadata else 'unknown'
            
            if doc_id not in groups:
                groups[doc_id] = []
            groups[doc_id].append(point)
        
        # Convert to DocumentGroup objects
        return {
            doc_id: DocumentGroup(document_id=doc_id, points=pts)
            for doc_id, pts in groups.items()
        }
    
    def fetch_document(self, document_id: str) -> Optional[DocumentGroup]:
        """
        Fetch all points for a specific document.
        
        Args:
            document_id: Document identifier
            
        Returns:
            DocumentGroup if found, None otherwise
        """
        all_points = self.fetch_all_points()
        groups = self.group_by_document(all_points)
        return groups.get(document_id)
    
    def list_documents(self) -> List[str]:
        """
        List all unique document IDs in the collection.
        
        Returns:
            List of document IDs
        """
        all_points = self.fetch_all_points()
        groups = self.group_by_document(all_points)
        return list(groups.keys())
