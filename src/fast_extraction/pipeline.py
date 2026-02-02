"""
Fast extraction pipeline orchestrator

Coordinates dual-path document processing:
1. Docling fast path for immediate metadata and guide generation
2. Unstructured API slow path for high-quality parsing (optional, future)
"""

import os
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from .models import DocumentStatus, SimpleMetadata, DocumentRecord
from .docling_extractor import DoclingExtractor
from .simple_metadata import SimpleMetadataExtractor
from .dedup_database import DeduplicationDatabase


class FastExtractionPipeline:
    """Orchestrates fast document extraction with deduplication"""
    
    def __init__(
        self,
        db_path: str = "fast_extraction_docs.db",
        output_dir: str = "output",
        model_name: Optional[str] = None
    ):
        """
        Initialize pipeline
        
        Args:
            db_path: Path to deduplication database
            output_dir: Directory to save metadata JSON files
            model_name: Groq model name (optional)
        """
        self.db = DeduplicationDatabase(db_path)
        self.metadata_extractor = SimpleMetadataExtractor(model_name)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def process_document(
        self,
        pdf_path: str,
        force_reprocess: bool = False
    ) -> Tuple[str, SimpleMetadata, bool]:
        """
        Process document with deduplication
        
        Args:
            pdf_path: Path to PDF file
            force_reprocess: If True, reprocess even if exists
            
        Returns:
            Tuple of (document_id, metadata, is_cached)
            - document_id: UUID string
            - metadata: SimpleMetadata object
            - is_cached: True if loaded from cache, False if newly processed
        """
        print(f"\n{'='*60}")
        print(f"📄 Processing: {Path(pdf_path).name}")
        print(f"{'='*60}\n")
        
        # Compute PDF hash
        print("🔐 Computing PDF hash...")
        pdf_hash = self.db.compute_pdf_hash(pdf_path)
        print(f"✅ Hash: {pdf_hash[:16]}...")
        
        # Check if document exists
        if not force_reprocess:
            existing = self.db.check_document(pdf_hash)
            if existing and existing.docling_metadata_path:
                print(f"\n✨ Document already processed!")
                print(f"📋 Document ID: {existing.document_id}")
                print(f"📄 Title: {existing.title}")
                print(f"📊 Status: {existing.status.value}")
                
                # Load cached metadata
                metadata = self._load_metadata(existing.docling_metadata_path)
                
                print(f"✅ Loaded cached metadata\n")
                return existing.document_id, metadata, True
        
        # Extract metadata (fast path)
        print("\n🚀 Starting fast extraction (Docling + Groq)...\n")
        
        # Create placeholder document record
        document_id = self.db.insert_document(
            pdf_hash=pdf_hash,
            title="Processing...",
            status=DocumentStatus.PROCESSING
        )
        
        try:
            # Extract metadata
            metadata = self.metadata_extractor.extract_metadata(
                pdf_path=pdf_path,
                document_id=document_id
            )
            
            # Save metadata to JSON
            metadata_path = self._save_metadata(metadata)
            
            # Update database
            self.db.update_status(
                document_id=document_id,
                status=DocumentStatus.DOCLING_READY,
                title=metadata.paper_title,
                docling_metadata_path=str(metadata_path)
            )
            
            print(f"\n{'='*60}")
            print(f"✅ Fast extraction complete!")
            print(f"{'='*60}")
            print(f"📋 Document ID: {document_id}")
            print(f"📄 Title: {metadata.paper_title}")
            print(f"📊 Sections: {len(metadata.sections)}")
            print(f"📈 Stats: {metadata.global_stats.total_pages} pages, "
                  f"{metadata.global_stats.total_formulas} formulas, "
                  f"{metadata.global_stats.total_tables} tables")
            print(f"💾 Metadata saved: {metadata_path}")
            print(f"{'='*60}\n")
            
            return document_id, metadata, False
        
        except Exception as e:
            # Mark as failed
            self.db.update_status(
                document_id=document_id,
                status=DocumentStatus.FAILED
            )
            raise RuntimeError(f"Fast extraction failed: {e}") from e
    
    def get_document_status(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get document processing status
        
        Args:
            document_id: UUID document identifier
            
        Returns:
            Dict with status info or None if not found
        """
        record = self.db.get_document_by_id(document_id)
        if not record:
            return None
        
        return {
            "document_id": record.document_id,
            "title": record.title,
            "status": record.status.value,
            "docling_ready": record.status in [
                DocumentStatus.DOCLING_READY,
                DocumentStatus.API_COMPLETE
            ],
            "api_ready": record.status == DocumentStatus.API_COMPLETE,
            "docling_metadata_path": record.docling_metadata_path,
            "api_metadata_path": record.api_metadata_path,
            "vectorstore_collection": record.vectorstore_collection,
            "created_at": record.created_at.isoformat() if record.created_at else None
        }
    
    def list_documents(
        self,
        status: Optional[DocumentStatus] = None,
        limit: Optional[int] = None
    ) -> list:
        """
        List all documents
        
        Args:
            status: Filter by status (None = all)
            limit: Maximum results
            
        Returns:
            List of document info dicts
        """
        records = self.db.get_all_documents(status=status, limit=limit)
        
        return [
            {
                "document_id": r.document_id,
                "title": r.title,
                "status": r.status.value,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in records
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        return self.db.get_statistics()
    
    def _save_metadata(self, metadata: SimpleMetadata) -> Path:
        """Save metadata to JSON file"""
        filename = f"{metadata.document_id}_docling_metadata.json"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata.model_dump(), f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def _load_metadata(self, metadata_path: str) -> SimpleMetadata:
        """Load metadata from JSON file"""
        with open(metadata_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return SimpleMetadata(**data)
    
    def generate_guide(
        self,
        document_id: str,
        guide_output_path: Optional[str] = None
    ) -> str:
        """
        Generate reading guide from metadata
        
        Args:
            document_id: UUID document identifier
            guide_output_path: Optional output path for guide JSON
            
        Returns:
            Path to generated guide JSON
        """
        # Get document record
        record = self.db.get_document_by_id(document_id)
        if not record:
            raise ValueError(f"Document {document_id} not found")
        
        if not record.docling_metadata_path:
            raise ValueError(f"Document {document_id} has no metadata")
        
        # Import guide generation (lazy import to avoid circular dependency)
        from src.guide_generation.minimal_guide_generation import generate_minimal_guide_llm
        
        # Set output path
        if guide_output_path is None:
            guide_output_path = self.output_dir / f"{document_id}_guide.json"
        
        print(f"\n{'='*60}")
        print(f"📖 Generating reading guide...")
        print(f"{'='*60}\n")
        
        # Generate guide
        guide = generate_minimal_guide_llm(
            metadata_path=record.docling_metadata_path,
            output_path=str(guide_output_path)
        )
        
        print(f"\n{'='*60}")
        print(f"✅ Guide generation complete!")
        print(f"{'='*60}")
        print(f"💾 Guide saved: {guide_output_path}")
        if hasattr(guide, 'passes'):
            print(f"📖 Total steps: {sum(len(p.steps) for p in guide.passes)}")
        print(f"{'='*60}\n")
        
        return str(guide_output_path)
