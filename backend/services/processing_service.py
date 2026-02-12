"""
Processing service wrapper.

Provides high-level interface for metadata extraction with:
- Integration with ingestion pipeline
- Caching
- Error handling
"""

import logging
from pathlib import Path
from typing import Optional

from backend.models.document import ValidatedDocument
from backend.models.metadata import ProcessedDocument
from backend.pipelines.metadata_pipeline import MetadataExtractionPipeline


logger = logging.getLogger(__name__)


class ProcessingService:
    """
    High-level service for document processing and metadata extraction.
    
    Provides a simplified API for extracting metadata from validated documents.
    """
    
    def __init__(
        self,
        pipeline: Optional[MetadataExtractionPipeline] = None,
    ):
        """
        Initialize processing service.
        
        Args:
            pipeline: Metadata extraction pipeline instance
        """
        if pipeline is None:
            self.pipeline = MetadataExtractionPipeline()
        else:
            self.pipeline = pipeline
    
    def process_document(
        self,
        document: ValidatedDocument
    ) -> ProcessedDocument:
        """
        Process a validated document to extract metadata.
        
        Args:
            document: ValidatedDocument from ingestion
            
        Returns:
            ProcessedDocument with extracted metadata
        """
        logger.info(f"Processing document {document.document_id}")
        
        try:
            processed = self.pipeline.process(document)
            logger.info(f"Successfully processed document {document.document_id}")
            return processed
            
        except Exception as e:
            logger.error(f"Error processing document {document.document_id}: {e}")
            raise
    
    def process_batch(
        self,
        documents: list[ValidatedDocument],
        continue_on_error: bool = True
    ) -> list[ProcessedDocument]:
        """
        Process multiple documents.
        
        Args:
            documents: List of ValidatedDocuments
            continue_on_error: Whether to continue if one fails
            
        Returns:
            List of ProcessedDocuments
        """
        logger.info(f"Processing batch of {len(documents)} documents")
        
        results = self.pipeline.process_batch(
            documents=documents,
            continue_on_error=continue_on_error
        )
        
        return results


class IntegratedPipeline:
    """
    Integrated pipeline for PDF ingestion and metadata extraction.
    
    Combines both pipelines into a single workflow:
    PDF -> Validation -> Extraction -> Metadata Extraction -> ProcessedDocument
    """
    
    def __init__(
        self,
        ingestion_pipeline=None,
        processing_service: Optional[ProcessingService] = None,
    ):
        """
        Initialize integrated pipeline.
        
        Args:
            ingestion_pipeline: PDF ingestion pipeline
            processing_service: Metadata extraction service
        """
        from backend.pipelines.ingest_pipeline import IngestPipeline
        
        self.ingestion_pipeline = ingestion_pipeline or IngestPipeline()
        self.processing_service = processing_service or ProcessingService()
    
    def ingest_and_process(
        self,
        pdf_path: str | Path,
    ) -> tuple[ValidatedDocument, ProcessedDocument]:
        """
        Ingest PDF and extract metadata in one call.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (ValidatedDocument, ProcessedDocument)
        """
        logger.info(f"Starting integrated pipeline for {pdf_path}")
        
        # Step 1: Ingest PDF
        validated_doc = self.ingestion_pipeline.process(Path(pdf_path))
        logger.info(f"Ingestion complete: {validated_doc.document_id}")
        
        # Step 2: Extract metadata
        processed_doc = self.processing_service.process_document(validated_doc)
        logger.info(f"Metadata extraction complete")
        
        return validated_doc, processed_doc
    
    def process_batch(
        self,
        pdf_paths: list[str | Path],
        continue_on_error: bool = True
    ) -> list[tuple[ValidatedDocument, ProcessedDocument]]:
        """
        Process multiple PDFs through the complete pipeline.
        
        Args:
            pdf_paths: List of PDF file paths
            continue_on_error: Whether to continue if one fails
            
        Returns:
            List of (ValidatedDocument, ProcessedDocument) tuples
        """
        results = []
        
        logger.info(f"Processing batch of {len(pdf_paths)} PDFs")
        
        for i, pdf_path in enumerate(pdf_paths, 1):
            try:
                logger.info(f"Processing PDF {i}/{len(pdf_paths)}: {pdf_path}")
                validated, processed = self.ingest_and_process(pdf_path)
                results.append((validated, processed))
                
            except Exception as e:
                logger.error(f"Error processing {pdf_path}: {e}")
                
                if not continue_on_error:
                    raise
        
        logger.info(f"Batch processing completed: {len(results)}/{len(pdf_paths)} successful")
        
        return results
