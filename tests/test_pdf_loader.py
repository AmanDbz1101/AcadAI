"""
Unit tests for PDF loader module.

Tests the PDFLoader class and text extraction logic.
"""

import pytest
from pathlib import Path

from backend.app.ingestion.pdf_loader import (
    PDFLoader,
    LoaderConfig,
)


class TestLoaderConfig:
    """Test suite for LoaderConfig."""
    
    def test_config_defaults(self):
        """Test default configuration values."""
        config = LoaderConfig()
        
        assert config.extract_images is True
        assert config.extract_tables is True
        assert config.do_ocr is False
        assert config.timeout_seconds == 120
    
    def test_config_custom(self):
        """Test custom configuration values."""
        config = LoaderConfig(
            extract_images=False,
            extract_tables=False,
            do_ocr=True,
            timeout_seconds=60,
        )
        
        assert config.extract_images is False
        assert config.extract_tables is False
        assert config.do_ocr is True
        assert config.timeout_seconds == 60


class TestPDFLoader:
    """Test suite for PDFLoader."""
    
    def test_loader_initialization_defaults(self):
        """Test loader initialization with default config."""
        loader = PDFLoader()
        
        assert loader.config is not None
        assert isinstance(loader.config, LoaderConfig)
    
    def test_loader_initialization_custom_config(self):
        """Test loader initialization with custom config."""
        config = LoaderConfig(extract_images=False)
        loader = PDFLoader(config=config)
        
        assert loader.config == config
        assert loader.config.extract_images is False
    
    def test_load_valid_pdf(self, sample_pdf_path):
        """Test loading a valid PDF file."""
        loader = PDFLoader()
        result = loader.load(sample_pdf_path)
        
        assert result is not None
        assert 'pages' in result
        assert 'full_text' in result
        assert 'page_count' in result
        assert 'processing_time' in result
        
        assert len(result['pages']) > 0
        assert len(result['full_text']) > 0
        assert result['page_count'] > 0
        assert result['processing_time'] > 0
    
    def test_load_multi_page_pdf(self, large_pdf_path):
        """Test loading a multi-page PDF."""
        loader = PDFLoader()
        result = loader.load(large_pdf_path)
        
        assert result['page_count'] == 5
        assert len(result['pages']) == 5
        
        # Verify each page has content
        for i, page in enumerate(result['pages'], 1):
            assert 'text' in page
            assert 'page_number' in page
            assert page['page_number'] == i
            assert len(page['text']) > 0
    
    def test_load_pages_have_required_fields(self, sample_pdf_path):
        """Test that loaded pages contain all required fields."""
        loader = PDFLoader()
        result = loader.load(sample_pdf_path)
        
        for page in result['pages']:
            assert hasattr(page, 'page_number')
            assert hasattr(page, 'text')
            assert hasattr(page, 'word_count')
            assert hasattr(page, 'char_count')
    
    def test_full_text_concatenation(self, large_pdf_path):
        """Test that full_text is properly concatenated from all pages."""
        loader = PDFLoader()
        result = loader.load(large_pdf_path)
        
        # Concatenate page texts manually
        expected_text = '\n\n'.join(page.text for page in result['pages'])
        
        assert result['full_text'] == expected_text
    
    def test_word_count_calculation(self, sample_pdf_path):
        """Test word count calculation for pages."""
        loader = PDFLoader()
        result = loader.load(sample_pdf_path)
        
        for page in result['pages']:
            # Manual word count
            manual_count = len(page.text.split())
            assert page.word_count > 0
            # Allow some tolerance for different word counting methods
            assert abs(page.word_count - manual_count) <= manual_count * 0.2
    
    def test_char_count_calculation(self, sample_pdf_path):
        """Test character count calculation for pages."""
        loader = PDFLoader()
        result = loader.load(sample_pdf_path)
        
        for page in result['pages']:
            assert page.char_count == len(page.text)
    
    def test_detect_readability_machine_readable(self, sample_pdf_path):
        """Test readability detection for machine-readable PDF."""
        loader = PDFLoader()
        result = loader.load(sample_pdf_path)
        
        readability = loader.detect_readability(result['pages'])
        
        assert 'is_machine_readable' in readability
        assert 'average_text_density' in readability
        assert 'pages_needing_ocr' in readability
        assert 'recommendation' in readability
        
        # Sample PDF should be machine readable
        assert readability['is_machine_readable'] is True
        assert readability['average_text_density'] > 50
        assert readability['pages_needing_ocr'] == 0
    
    def test_detect_readability_scanned_pdf(self, scanned_pdf_path):
        """Test readability detection for scanned PDF."""
        loader = PDFLoader()
        result = loader.load(scanned_pdf_path)
        
        readability = loader.detect_readability(result['pages'])
        
        # Scanned PDF should have low text density
        assert readability['is_machine_readable'] is False
        assert readability['average_text_density'] < 50
        assert readability['pages_needing_ocr'] > 0
        assert 'OCR' in readability['recommendation']
    
    def test_load_file_not_found(self, tmp_path):
        """Test loading a non-existent file."""
        loader = PDFLoader()
        non_existent = tmp_path / "does_not_exist.pdf"
        
        with pytest.raises(Exception):  # Should raise FileNotFoundError or similar
            loader.load(non_existent)
    
    def test_load_corrupted_pdf(self, corrupted_pdf_path):
        """Test loading a corrupted PDF."""
        loader = PDFLoader()
        
        with pytest.raises(Exception):  # Should raise an error
            loader.load(corrupted_pdf_path)
    
    def test_processing_time_recorded(self, sample_pdf_path):
        """Test that processing time is recorded."""
        loader = PDFLoader()
        result = loader.load(sample_pdf_path)
        
        assert result['processing_time'] > 0
        assert isinstance(result['processing_time'], float)
    
    def test_text_extraction_quality(self, sample_pdf_path):
        """Test that extracted text contains expected content."""
        loader = PDFLoader()
        result = loader.load(sample_pdf_path)
        
        full_text = result['full_text'].lower()
        
        # Check for expected keywords from our test PDF
        assert 'research' in full_text or 'paper' in full_text or 'abstract' in full_text
    
    def test_page_numbering_sequential(self, large_pdf_path):
        """Test that page numbers are sequential and start from 1."""
        loader = PDFLoader()
        result = loader.load(large_pdf_path)
        
        page_numbers = [page.page_number for page in result['pages']]
        expected_numbers = list(range(1, result['page_count'] + 1))
        
        assert page_numbers == expected_numbers


class TestTextDensityCalculation:
    """Test suite for text density calculations."""
    
    def test_high_density_page(self, sample_pdf_path):
        """Test text density calculation for high-density page."""
        loader = PDFLoader()
        result = loader.load(sample_pdf_path)
        
        # Sample PDF should have high text density
        first_page = result['pages'][0]
        assert first_page.char_count > 50
    
    def test_low_density_page(self, scanned_pdf_path):
        """Test text density calculation for low-density page."""
        loader = PDFLoader()
        result = loader.load(scanned_pdf_path)
        
        # Scanned PDF should have low text density
        first_page = result['pages'][0]
        assert first_page.char_count < 50
    
    def test_average_text_density(self, large_pdf_path):
        """Test average text density calculation across pages."""
        loader = PDFLoader()
        result = loader.load(large_pdf_path)
        
        readability = loader.detect_readability(result['pages'])
        
        # Calculate manual average
        total_chars = sum(page.char_count for page in result['pages'])
        manual_avg = total_chars / len(result['pages'])
        
        assert abs(readability['average_text_density'] - manual_avg) < 1.0
