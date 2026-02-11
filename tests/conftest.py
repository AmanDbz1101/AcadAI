"""
Pytest configuration and shared fixtures for testing.
"""

import io
import sys
from pathlib import Path
from typing import Generator

import pytest
import pymupdf

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """Create a simple test PDF file."""
    pdf_path = tmp_path / "test_document.pdf"
    
    # Create a simple PDF with text
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4 size
    
    # Add some text content
    text = """
    Research Paper Title
    
    Abstract
    This is a sample research paper for testing the PDF ingestion pipeline.
    It contains multiple paragraphs and sufficient text for validation.
    
    Introduction
    The introduction section provides background information about the research.
    This document is created specifically for unit testing purposes.
    
    Methodology
    We describe the methods used in this research.
    Multiple sentences ensure adequate text density.
    
    Results
    The results section presents the findings.
    """
    
    text_rect = pymupdf.Rect(50, 50, 545, 792)
    page.insert_textbox(text_rect, text, fontsize=11, align=0)
    
    doc.save(pdf_path)
    doc.close()
    
    return pdf_path


@pytest.fixture
def empty_pdf_path(tmp_path: Path) -> Path:
    """Create an empty PDF file (single page with no content)."""
    pdf_path = tmp_path / "empty.pdf"
    
    # Create PDF with one empty page
    doc = pymupdf.open()
    page = doc.new_page()  # Empty page, no content
    doc.save(pdf_path)
    doc.close()
    
    return pdf_path


@pytest.fixture
def scanned_pdf_path(tmp_path: Path) -> Path:
    """Create a PDF that simulates a scanned document (low text density)."""
    pdf_path = tmp_path / "scanned.pdf"
    
    # Create a PDF with minimal text (simulating scanned image)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    
    # Add very little text to simulate scanned page
    text = "Page 1"
    text_rect = pymupdf.Rect(50, 50, 100, 70)
    page.insert_textbox(text_rect, text, fontsize=11)
    
    doc.save(pdf_path)
    doc.close()
    
    return pdf_path


@pytest.fixture
def encrypted_pdf_path(tmp_path: Path) -> Path:
    """Create an encrypted PDF file."""
    pdf_path = tmp_path / "encrypted.pdf"
    
    # Create and encrypt a PDF
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Encrypted content")
    
    # Encrypt with password
    perm = int(
        pymupdf.PDF_PERM_ACCESSIBILITY
        | pymupdf.PDF_PERM_PRINT
        | pymupdf.PDF_PERM_COPY
        | pymupdf.PDF_PERM_ANNOTATE
    )
    encrypt_meth = pymupdf.PDF_ENCRYPT_AES_256
    
    doc.save(
        pdf_path,
        encryption=encrypt_meth,
        owner_pw="owner",
        user_pw="user",
        permissions=perm,
    )
    doc.close()
    
    return pdf_path


@pytest.fixture
def large_pdf_path(tmp_path: Path) -> Path:
    """Create a multi-page PDF for testing."""
    pdf_path = tmp_path / "large_document.pdf"
    
    doc = pymupdf.open()
    
    # Create 5 pages with different content
    for i in range(5):
        page = doc.new_page(width=595, height=842)
        text = f"""
        Page {i + 1}
        
        This is page {i + 1} of the test document.
        Each page contains unique content for testing.
        
        Lorem ipsum dolor sit amet, consectetur adipiscing elit.
        Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
        Ut enim ad minim veniam, quis nostrud exercitation ullamco.
        
        Section {i + 1}
        Additional content to ensure adequate text density.
        Multiple paragraphs help test word counting functionality.
        """
        
        text_rect = pymupdf.Rect(50, 50, 545, 792)
        page.insert_textbox(text_rect, text, fontsize=11)
    
    doc.save(pdf_path)
    doc.close()
    
    return pdf_path


@pytest.fixture
def corrupted_pdf_path(tmp_path: Path) -> Path:
    """Create a corrupted PDF file."""
    pdf_path = tmp_path / "corrupted.pdf"
    
    # Write invalid PDF data
    with open(pdf_path, "wb") as f:
        f.write(b"This is not a valid PDF file")
    
    return pdf_path


@pytest.fixture
def non_pdf_path(tmp_path: Path) -> Path:
    """Create a non-PDF file."""
    file_path = tmp_path / "document.txt"
    file_path.write_text("This is a text file, not a PDF")
    return file_path
