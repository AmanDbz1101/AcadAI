"""
Integration tests for the complete ingestion module.

Tests end-to-end workflows and component integration.
"""

import pytest
from pathlib import Path

from backend.pipelines.ingest_pipeline import IngestPipeline
from backend.services.ingestion_service import IngestionService
from backend.models.document import DocumentStatus


class TestEndToEndIngestion:
    """Test end-to-end ingestion workflows."""
    
    def test_complete_workflow_valid_pdf(self, sample_pdf_path):
        """Test complete ingestion workflow with valid PDF."""
        pipeline = IngestPipeline()
        
        # Process the PDF
        document = pipeline.process(sample_pdf_path)
        
        # Verify complete workflow results
        assert document.status == DocumentStatus.COMPLETED
        assert document.document_id is not None
        assert document.pdf_hash is not None
        assert len(document.pages) > 0
        assert document.full_text is not None
        assert document.processing_time_seconds > 0
        
        # Verify content quality
        assert document.total_word_count > 10
        assert document.total_char_count > 50
        
        # Verify each page has content
        for page in document.pages:
            assert len(page.text) > 0
            assert page.word_count > 0
    
    def test_workflow_with_multiple_pages(self, large_pdf_path):
        """Test workflow with multi-page document."""
        pipeline = IngestPipeline()
        document = pipeline.process(large_pdf_path)
        
        # Verify all pages processed
        assert document.page_count == 5
        assert len(document.pages) == 5
        
        # Verify pages are in order
        for i, page in enumerate(document.pages, 1):
            assert page.page_number == i
        
        # Verify text concatenation
        combined_text = '\n\n'.join(page.text for page in document.pages)
        assert document.full_text == combined_text
    
    def test_workflow_preserves_metadata(self, sample_pdf_path):
        """Test that metadata is preserved through workflow."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        # Verify file metadata
        assert document.pdf_path == sample_pdf_path
        assert document.file_size_bytes == sample_pdf_path.stat().st_size
        
        # Verify processing metadata
        assert document.processing_time_seconds > 0


class TestServiceLayerIntegration:
    """Test integration with service layer."""
    
    def test_service_basic_ingestion(self, sample_pdf_path, tmp_path):
        """Test basic ingestion through service layer."""
        service = IngestionService(
            cache_dir=tmp_path / "cache",
            enable_deduplication=True,
        )
        
        document = service.ingest(sample_pdf_path)
        
        assert document is not None
        assert document.status == DocumentStatus.COMPLETED
    
    def test_service_deduplication(self, sample_pdf_path, tmp_path):
        """Test deduplication in service layer."""
        service = IngestionService(
            cache_dir=tmp_path / "cache",
            enable_deduplication=True,
        )
        
        # Ingest first time
        doc1 = service.ingest(sample_pdf_path)
        
        # Check for duplicate
        duplicate_id = service.is_duplicate(sample_pdf_path)
        
        assert duplicate_id is not None
        assert duplicate_id == doc1.document_id
    
    def test_service_batch_processing(
        self, sample_pdf_path, large_pdf_path, tmp_path
    ):
        """Test batch processing through service layer."""
        service = IngestionService(
            cache_dir=tmp_path / "cache",
            enable_deduplication=True,
        )
        
        pdf_paths = [sample_pdf_path, large_pdf_path]
        results = service.ingest_batch(pdf_paths)
        
        assert len(results['successful']) == 2
        assert len(results['failed']) == 0
    
    def test_service_progress_callback(self, sample_pdf_path, tmp_path):
        """Test progress callback in service layer."""
        service = IngestionService(cache_dir=tmp_path / "cache")
        
        progress_calls = []
        
        def progress_callback(message: str, pct: float):
            progress_calls.append((message, pct))
        
        document = service.ingest(
            sample_pdf_path,
            progress_callback=progress_callback
        )
        
        # Verify progress was reported
        assert len(progress_calls) > 0
        assert document.status == DocumentStatus.COMPLETED
    
    def test_service_statistics(self, sample_pdf_path, tmp_path):
        """Test service statistics tracking."""
        service = IngestionService(cache_dir=tmp_path / "cache")
        
        # Process a document
        service.ingest(sample_pdf_path)
        
        # Get stats
        stats = service.get_stats()
        
        assert 'processed_documents' in stats
        assert stats['processed_documents'] >= 1


class TestPerformance:
    """Test performance characteristics."""
    
    def test_processing_time_reasonable(self, sample_pdf_path):
        """Test that processing completes in reasonable time."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        # Should complete in under 30 seconds for small PDF
        assert document.processing_time_seconds < 30.0
    
    def test_batch_processing_efficiency(self, tmp_path):
        """Test that batch processing is efficient."""
        import time
        
        # Create multiple test PDFs
        import pymupdf
        pdf_paths = []
        
        for i in range(3):
            pdf_path = tmp_path / f"test_{i}.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((50, 50), f"Test document {i}")
            doc.save(pdf_path)
            doc.close()
            pdf_paths.append(pdf_path)
        
        pipeline = IngestPipeline()
        
        # Time batch processing
        start_time = time.time()
        results = pipeline.process_batch(pdf_paths)
        batch_time = time.time() - start_time
        
        assert len(results['successful']) == 3
        # Batch should be reasonably fast
        assert batch_time < 60.0


class TestRobustness:
    """Test robustness and edge cases."""
    
    def test_handles_special_characters_in_path(self, tmp_path):
        """Test handling of special characters in file path."""
        import pymupdf
        
        # Create PDF with special characters in name
        pdf_path = tmp_path / "test file (with special).pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Test content")
        doc.save(pdf_path)
        doc.close()
        
        pipeline = IngestPipeline()
        document = pipeline.process(pdf_path)
        
        assert document.status == DocumentStatus.COMPLETED
    
    def test_handles_unicode_content(self, tmp_path):
        """Test handling of Unicode content in PDFs."""
        import pymupdf
        
        pdf_path = tmp_path / "unicode_test.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        
        # Add Unicode text
        unicode_text = "Hello 世界 Привет مرحبا"
        page.insert_text((50, 50), unicode_text)
        doc.save(pdf_path)
        doc.close()
        
        pipeline = IngestPipeline()
        document = pipeline.process(pdf_path)
        
        assert document.status == DocumentStatus.COMPLETED
        assert len(document.full_text) > 0
    
    def test_handles_very_small_pdf(self, tmp_path):
        """Test handling of very small PDFs."""
        import pymupdf
        
        pdf_path = tmp_path / "tiny.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=100, height=100)
        page.insert_text((10, 10), "Hi")
        doc.save(pdf_path)
        doc.close()
        
        pipeline = IngestPipeline()
        document = pipeline.process(pdf_path)
        
        assert document.status == DocumentStatus.COMPLETED


class TestDataConsistency:
    """Test data consistency across pipeline."""
    
    def test_page_count_consistency(self, large_pdf_path):
        """Test page count is consistent across fields."""
        pipeline = IngestPipeline()
        document = pipeline.process(large_pdf_path)
        
        assert document.page_count == len(document.pages)
        
        # Verify each page number
        for i, page in enumerate(document.pages, 1):
            assert page.page_number == i
    
    def test_text_length_consistency(self, sample_pdf_path):
        """Test text length is consistent."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        # Full text length should equal total char count
        assert len(document.full_text) == document.total_char_count
        
        # Sum of page char counts should match
        page_char_sum = sum(len(page.text) for page in document.pages)
        
        # Account for page separators in full_text
        separator_chars = (len(document.pages) - 1) * 2  # '\n\n' between pages
        assert len(document.full_text) == page_char_sum + separator_chars
    
    def test_word_count_consistency(self, sample_pdf_path):
        """Test word count is consistent."""
        pipeline = IngestPipeline()
        document = pipeline.process(sample_pdf_path)
        
        # Total word count should be approximately sum of page word counts
        page_word_sum = sum(page.word_count for page in document.pages)
        
        # Allow small tolerance for counting differences
        assert abs(document.total_word_count - page_word_sum) <= page_word_sum * 0.1
