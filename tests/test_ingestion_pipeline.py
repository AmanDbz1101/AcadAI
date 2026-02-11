"""
Unit tests for the ingestion pipeline.

Tests the complete IngestPipeline orchestration.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from backend.pipelines.ingest_pipeline import (
    IngestPipeline,
    ValidationError,
    ExtractionError,
)
from backend.models.document import ValidatedDocument, DocumentStatus
from backend.app.ingestion.validation import PDFValidator
from backend.app.ingestion.pdf_loader import PDFLoader
from backend.app.ingestion.ocr import OCRHandler


class TestIngestPipelineInitialization:
    """Test suite for pipeline initialization."""
    
    def test_pipeline_default_initialization(self):
        """Test pipeline initialization with defaults."""
        pipeline = IngestPipeline()
        
        assert pipeline.validator is not None
        assert pipeline.loader is not None
        assert pipeline.ocr_handler is not None
        assert pipeline.enable_ocr is True
    
    def test_pipeline_custom_components(self):
        """Test pipeline initialization with custom components."""
        validator = PDFValidator(max_file_size_mb=100)
        loader = PDFLoader()
        ocr_handler = OCRHandler()
        
        pipeline = IngestPipeline(
            validator=validator,
            loader=loader,
            ocr_handler=ocr_handler,
            enable_ocr=False,
        )
        
        assert pipeline.validator == validator
        assert pipeline.loader == loader
        assert pipeline.ocr_handler == ocr_handler
        assert pipeline.enable_ocr is False


class TestIngestPipelineProcess:
    """Test suite for pipeline processing."""
    
    def test_process_valid_pdf(self, sample_pdf_path):
        """Test processing a valid PDF through the pipeline."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        assert isinstance(document, ValidatedDocument)
        assert document.document_id is not None
        assert document.pdf_path == sample_pdf_path
        assert document.page_count > 0
        assert document.status == DocumentStatus.COMPLETED
        assert len(document.pages) > 0
        assert document.processing_time_seconds > 0
    
    def test_process_creates_document_id(self, sample_pdf_path):
        """Test that processing creates a unique document ID."""
        pipeline = IngestPipeline()
        
        doc1 = pipeline.process(sample_pdf_path)
        doc2 = pipeline.process(sample_pdf_path)
        
        assert doc1.document_id != doc2.document_id
    
    def test_process_calculates_hash(self, sample_pdf_path):
        """Test that processing calculates PDF hash."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        assert document.pdf_hash is not None
        assert len(document.pdf_hash) == 64  # SHA256
    
    def test_process_same_pdf_same_hash(self, sample_pdf_path):
        """Test that same PDF produces same hash."""
        pipeline = IngestPipeline()
        
        doc1 = pipeline.process(sample_pdf_path)
        doc2 = pipeline.process(sample_pdf_path)
        
        assert doc1.pdf_hash == doc2.pdf_hash
    
    def test_process_extracts_text(self, sample_pdf_path):
        """Test that processing extracts text content."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        assert document.full_text is not None
        assert len(document.full_text) > 0
        assert document.total_word_count > 0
        assert document.total_char_count > 0
    
    def test_process_creates_pages(self, large_pdf_path):
        """Test that processing creates page objects."""
        pipeline = IngestPipeline()
        document = pipeline.process(large_pdf_path)
        
        assert len(document.pages) == 5
        
        for i, page in enumerate(document.pages, 1):
            assert page.page_number == i
            assert len(page.text) > 0
            assert page.word_count > 0
    
    def test_process_validation_failure(self, corrupted_pdf_path):
        """Test that validation errors are raised."""
        pipeline = IngestPipeline()
        
        with pytest.raises(ValidationError):
            pipeline.process(corrupted_pdf_path)
    
    def test_process_file_not_found(self, tmp_path):
        """Test processing non-existent file."""
        pipeline = IngestPipeline()
        non_existent = tmp_path / "does_not_exist.pdf"
        
        with pytest.raises((ValidationError, FileNotFoundError)):
            pipeline.process(non_existent)
    
    def test_process_with_ocr_disabled(self, scanned_pdf_path):
        """Test processing with OCR disabled."""
        pipeline = IngestPipeline(enable_ocr=False)
        document = pipeline.process(scanned_pdf_path)
        
        assert document.status == DocumentStatus.COMPLETED
        # OCR should not have been applied
        if document.ocr_metadata:
            assert document.ocr_metadata.was_ocr_applied is False
    
    def test_process_records_timing(self, sample_pdf_path):
        """Test that processing time is recorded."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        assert document.processing_time_seconds > 0
        assert isinstance(document.processing_time_seconds, float)
    
    def test_process_sets_file_size(self, sample_pdf_path):
        """Test that file size is recorded."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        assert document.file_size_bytes > 0
        assert document.file_size_bytes == sample_pdf_path.stat().st_size


class TestIngestPipelineBatchProcessing:
    """Test suite for batch processing."""
    
    def test_batch_process_multiple_pdfs(self, sample_pdf_path, large_pdf_path):
        """Test batch processing of multiple PDFs."""
        pipeline = IngestPipeline()
        pdf_paths = [sample_pdf_path, large_pdf_path]
        
        results = pipeline.process_batch(pdf_paths)
        
        assert 'successful' in results
        assert 'failed' in results
        assert len(results['successful']) == 2
        assert len(results['failed']) == 0
    
    def test_batch_process_with_failures(self, sample_pdf_path, corrupted_pdf_path):
        """Test batch processing with some failures."""
        pipeline = IngestPipeline()
        pdf_paths = [sample_pdf_path, corrupted_pdf_path]
        
        results = pipeline.process_batch(
            pdf_paths,
            continue_on_error=True
        )
        
        assert len(results['successful']) == 1
        assert len(results['failed']) == 1
        assert results['successful'][0].pdf_path == sample_pdf_path
    
    def test_batch_process_empty_list(self):
        """Test batch processing with empty list."""
        pipeline = IngestPipeline()
        results = pipeline.process_batch([])
        
        assert len(results['successful']) == 0
        assert len(results['failed']) == 0
    
    def test_batch_process_stop_on_error(self, sample_pdf_path, corrupted_pdf_path):
        """Test batch processing stops on error when configured."""
        pipeline = IngestPipeline()
        pdf_paths = [corrupted_pdf_path, sample_pdf_path]
        
        results = pipeline.process_batch(
            pdf_paths,
            continue_on_error=False
        )
        
        # Should stop after first failure
        assert len(results['failed']) >= 1


class TestDocumentModel:
    """Test suite for ValidatedDocument model."""
    
    def test_document_has_required_fields(self, sample_pdf_path):
        """Test that document has all required fields."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        # Core identification
        assert hasattr(document, 'document_id')
        assert hasattr(document, 'pdf_path')
        assert hasattr(document, 'pdf_hash')
        
        # Content
        assert hasattr(document, 'pages')
        assert hasattr(document, 'full_text')
        assert hasattr(document, 'page_count')
        
        # Metadata
        assert hasattr(document, 'file_size_bytes')
        assert hasattr(document, 'total_word_count')
        assert hasattr(document, 'total_char_count')
        
        # Processing info
        assert hasattr(document, 'status')
        assert hasattr(document, 'processing_time_seconds')
    
    def test_document_get_page(self, large_pdf_path):
        """Test retrieving individual pages."""
        pipeline = IngestPipeline()
        document = pipeline.process(large_pdf_path)
        
        # Get page 3
        page_3 = document.get_page(3)
        assert page_3 is not None
        assert page_3.page_number == 3
        
        # Get non-existent page
        page_100 = document.get_page(100)
        assert page_100 is None
    
    def test_document_get_text_range(self, large_pdf_path):
        """Test retrieving text from page range."""
        pipeline = IngestPipeline()
        document = pipeline.process(large_pdf_path)
        
        # Get pages 1-3
        text = document.get_text_range(1, 3)
        assert len(text) > 0
        
        # Should contain text from all three pages
        page_1_text = document.get_page(1).text
        page_3_text = document.get_page(3).text
        
        assert page_1_text in text
        assert page_3_text in text
    
    def test_document_word_count_sum(self, large_pdf_path):
        """Test that total word count is sum of page word counts."""
        pipeline = IngestPipeline()
        document = pipeline.process(large_pdf_path)
        
        manual_sum = sum(page.word_count for page in document.pages)
        
        # Allow some tolerance
        assert abs(document.total_word_count - manual_sum) <= manual_sum * 0.1
    
    def test_document_char_count_matches_text(self, sample_pdf_path):
        """Test that char count matches full text length."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        assert document.total_char_count == len(document.full_text)


class TestDeduplication:
    """Test suite for deduplication logic."""
    
    def test_same_pdf_produces_same_hash(self, sample_pdf_path):
        """Test that processing same PDF produces same hash."""
        pipeline = IngestPipeline()
        
        doc1 = pipeline.process(sample_pdf_path)
        doc2 = pipeline.process(sample_pdf_path)
        
        assert doc1.pdf_hash == doc2.pdf_hash
    
    def test_different_pdfs_produce_different_hashes(
        self, sample_pdf_path, large_pdf_path
    ):
        """Test that different PDFs produce different hashes."""
        pipeline = IngestPipeline()
        
        doc1 = pipeline.process(sample_pdf_path)
        doc2 = pipeline.process(large_pdf_path)
        
        assert doc1.pdf_hash != doc2.pdf_hash
    
    def test_hash_is_consistent(self, sample_pdf_path):
        """Test hash consistency across multiple runs."""
        pipeline = IngestPipeline()
        
        hashes = []
        for _ in range(3):
            doc = pipeline.process(sample_pdf_path)
            hashes.append(doc.pdf_hash)
        
        # All hashes should be identical
        assert len(set(hashes)) == 1


class TestErrorHandling:
    """Test suite for error handling."""
    
    def test_handles_corrupted_pdf(self, corrupted_pdf_path):
        """Test handling of corrupted PDFs."""
        pipeline = IngestPipeline()
        
        with pytest.raises((ValidationError, ExtractionError, Exception)):
            pipeline.process(corrupted_pdf_path)
    
    def test_handles_encrypted_pdf(self, encrypted_pdf_path):
        """Test handling of encrypted PDFs."""
        pipeline = IngestPipeline()
        
        with pytest.raises((ValidationError, Exception)):
            pipeline.process(encrypted_pdf_path)
    
    def test_handles_empty_pdf(self, empty_pdf_path):
        """Test handling of empty PDFs."""
        pipeline = IngestPipeline()
        
        with pytest.raises((ValidationError, Exception)):
            pipeline.process(empty_pdf_path)
