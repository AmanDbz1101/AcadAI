"""
Metadata extraction pipeline.

Orchestrates the complete metadata extraction workflow using
Docling + Groq approach for accurate extraction.
"""

import time
import logging
from pathlib import Path
from typing import Optional

from backend.models.document import ValidatedDocument
from backend.models.metadata import ExtractedMetadata, ProcessedDocument
from backend.app.processing.metadata_extractor_v2 import MetadataExtractor
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


class MetadataExtractionPipeline:
    """
    Orchestrates metadata extraction from validated documents.
    
    Uses Docling for structure extraction and Groq LLM for classification.
    """
    
    def __init__(
        self,
        groq_api_key: Optional[str] = None,
    ):
        """
        Initialize metadata extraction pipeline.
        
        Args:
            groq_api_key: Groq API key for LLM (defaults to env var)
        """
        # Initialize extractor
        self.extractor = MetadataExtractor(api_key=groq_api_key)
    
    def process(self, document: ValidatedDocument) -> ProcessedDocument:
        """
        Process a validated document to extract metadata.
        
        Args:
            document: ValidatedDocument from ingestion pipeline
            
        Returns:
            ProcessedDocument with extracted metadata
        """
        logger.info(f"Starting metadata extraction for document {document.document_id}")
        start_time = time.time()
        
        # Extract metadata using Docling + Groq approach
        metadata = self.extractor.extract(document)
        
        # Create processed document
        processing_time = time.time() - start_time
        
        processed_doc = ProcessedDocument(
            document_id=document.document_id,
            metadata=metadata,
            processing_time_seconds=processing_time
        )
        
        logger.info(
            f"Metadata extraction completed in {processing_time:.2f}s. "
            f"Coverage: {metadata.get_field_coverage():.2%}"
        )
        
        return processed_doc
    
    def process_batch(
        self,
        documents: list[ValidatedDocument],
        continue_on_error: bool = True
    ) -> list[ProcessedDocument]:
        """
        Process multiple documents.
        
        Args:
            documents: List of ValidatedDocuments
            continue_on_error: Whether to continue if one document fails
            
        Returns:
            List of ProcessedDocuments
        """
        results = []
        
        logger.info(f"Processing batch of {len(documents)} documents")
        
        for i, document in enumerate(documents, 1):
            try:
                logger.info(f"Processing document {i}/{len(documents)}")
                processed = self.process(document)
                results.append(processed)
                
            except Exception as e:
                logger.error(f"Error processing document {document.document_id}: {e}")
                
                if not continue_on_error:
                    raise
                
                # Create a failed result
                results.append(ProcessedDocument(
                    document_id=document.document_id,
                    metadata=ExtractedMetadata(),
                    processing_time_seconds=0
                ))
        
        logger.info(f"Batch processing completed: {len(results)}/{len(documents)} successful")
        
        return results
