"""
Ingestion service wrapper.

Provides high-level interface for PDF ingestion with:
- Caching
- Logging
- Deduplication tracking
- Progress callbacks
"""

import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any
from uuid import UUID
import json

from backend.models.document import ValidatedDocument
from backend.pipelines.ingest_pipeline import IngestPipeline, IngestionError


logger = logging.getLogger(__name__)


class IngestionService:
    """
    High-level service for PDF ingestion.
    
    Features:
    - Simplified API for document ingestion
    - Optional caching of processed documents
    - Deduplication by file hash
    - Progress callbacks for long operations
    """
    
    def __init__(
        self,
        pipeline: Optional[IngestPipeline] = None,
        cache_dir: Optional[Path] = None,
        enable_deduplication: bool = True,
    ):
        """
        Initialize ingestion service.
        
        Args:
            pipeline: Ingestion pipeline instance
            cache_dir: Directory for caching processed documents
            enable_deduplication: Enable hash-based deduplication
        """
        self.pipeline = pipeline or IngestPipeline()
        self.cache_dir = cache_dir
        self.enable_deduplication = enable_deduplication
        self._processed_hashes: Dict[str, UUID] = {}  # hash -> document_id
        
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cache enabled: {self.cache_dir}")
    
    def ingest(
        self,
        pdf_path: Path,
        force_reprocess: bool = False,
        force_ocr: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> ValidatedDocument:
        """
        Ingest a PDF file.
        
        Args:
            pdf_path: Path to PDF file
            force_reprocess: Reprocess even if cached
            force_ocr: Force OCR regardless of text density
            progress_callback: Callback for progress updates (message, progress_pct)
            
        Returns:
            ValidatedDocument
            
        Raises:
            IngestionError: If ingestion fails
        """
        # Convert to Path
        if isinstance(pdf_path, str):
            pdf_path = Path(pdf_path)
        
        logger.info(f"Ingesting: {pdf_path.name}")
        
        # Check cache
        if not force_reprocess and self.cache_dir:
            cached = self._load_from_cache(pdf_path)
            if cached:
                logger.info(f"Loaded from cache: {pdf_path.name}")
                if progress_callback:
                    progress_callback("Loaded from cache", 100.0)
                return cached
        
        # Progress: Validation
        if progress_callback:
            progress_callback("Validating PDF", 10.0)
        
        # Process through pipeline
        try:
            document = self.pipeline.process(
                pdf_path=pdf_path,
                force_ocr=force_ocr,
            )
            
            # Progress: Completed
            if progress_callback:
                progress_callback("Ingestion completed", 100.0)
            
            # Cache result
            if self.cache_dir:
                self._save_to_cache(document)
            
            # Track for deduplication
            if self.enable_deduplication:
                self._processed_hashes[document.pdf_hash] = document.document_id
            
            return document
            
        except Exception as e:
            logger.error(f"Ingestion failed for {pdf_path.name}: {str(e)}")
            if progress_callback:
                progress_callback(f"Failed: {str(e)}", 0.0)
            raise
    
    def is_duplicate(self, pdf_path: Path) -> Optional[UUID]:
        """
        Check if PDF has already been processed.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Document ID if duplicate found, None otherwise
        """
        if not self.enable_deduplication:
            return None
        
        # Calculate hash
        import hashlib
        sha256_hash = hashlib.sha256()
        with open(pdf_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        pdf_hash = sha256_hash.hexdigest()
        
        return self._processed_hashes.get(pdf_hash)
    
    def _load_from_cache(self, pdf_path: Path) -> Optional[ValidatedDocument]:
        """
        Load document from cache.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Cached ValidatedDocument or None
        """
        if not self.cache_dir:
            return None
        
        # Generate cache key from filename
        cache_key = pdf_path.stem
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            
            # Reconstruct ValidatedDocument
            document = ValidatedDocument.model_validate(data)
            return document
            
        except Exception as e:
            logger.warning(f"Failed to load from cache: {str(e)}")
            return None
    
    def _save_to_cache(self, document: ValidatedDocument) -> None:
        """
        Save document to cache.
        
        Args:
            document: ValidatedDocument to cache
        """
        if not self.cache_dir:
            return
        
        cache_key = document.pdf_path.stem
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(document.model_dump(mode='json'), f, indent=2)
            
            logger.debug(f"Cached to: {cache_file}")
            
        except Exception as e:
            logger.warning(f"Failed to cache document: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get ingestion service statistics.
        
        Returns:
            Dictionary with service stats
        """
        return {
            "processed_documents": len(self._processed_hashes),
            "cache_enabled": self.cache_dir is not None,
            "deduplication_enabled": self.enable_deduplication,
        }
