#!/usr/bin/env python3
"""
Quick test script for the PDF Ingestion module.

Tests basic functionality without requiring a full API setup.
"""

import sys
from pathlib import Path

# Add project root to path (parent of backend directory)
backend_dir = Path(__file__).parent
project_root = backend_dir.parent
sys.path.insert(0, str(project_root))

from backend.app.ingestion import PDFValidator, PDFLoader, OCRHandler
from backend.pipelines import IngestPipeline


def test_validator():
    """Test PDF validator."""
    print("Testing PDF Validator...")
    
    validator = PDFValidator(max_file_size_mb=50)
    
    # Test with a sample PDF (you'll need to provide one)
    test_pdf = Path("Research Papers").glob("*.pdf")
    test_pdf = next(test_pdf, None)
    
    if test_pdf and test_pdf.exists():
        result = validator.validate(test_pdf)
        print(f"✓ Validation: {'PASS' if result.is_valid else 'FAIL'}")
        if result.is_valid:
            print(f"  Pages: {result.page_count}")
            print(f"  Size: {result.file_size_bytes / 1024:.1f} KB")
    else:
        print("⚠ No test PDF found - skipping validation test")
    
    print()


def test_loader():
    """Test PDF loader."""
    print("Testing PDF Loader...")
    
    loader = PDFLoader()
    
    test_pdf = Path("Research Papers").glob("*.pdf")
    test_pdf = next(test_pdf, None)
    
    if test_pdf and test_pdf.exists():
        result = loader.load(test_pdf)
        print(f"✓ Extraction successful")
        print(f"  Pages: {len(result['pages'])}")
        print(f"  Characters: {len(result['full_text']):,}")
        print(f"  Time: {result['processing_time']:.2f}s")
        
        # Test readability detection
        readability = loader.detect_readability(result['pages'])
        print(f"  Readable: {readability['is_machine_readable']}")
    else:
        print("⚠ No test PDF found - skipping loader test")
    
    print()


def test_pipeline():
    """Test complete ingestion pipeline."""
    print("Testing Complete Pipeline...")
    
    pipeline = IngestPipeline()
    
    test_pdf = Path("Research Papers").glob("*.pdf")
    test_pdf = next(test_pdf, None)
    
    if test_pdf and test_pdf.exists():
        try:
            document = pipeline.process(test_pdf)
            print(f"✓ Pipeline successful")
            print(f"  Document ID: {document.document_id}")
            print(f"  Pages: {document.page_count}")
            print(f"  Words: {document.total_word_count:,}")
            print(f"  Status: {document.status}")
        except Exception as e:
            print(f"✗ Pipeline failed: {str(e)}")
    else:
        print("⚠ No test PDF found - skipping pipeline test")
    
    print()


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PDF Ingestion Module - Quick Test")
    print("=" * 60 + "\n")
    
    test_validator()
    test_loader()
    test_pipeline()
    
    print("=" * 60)
    print("Testing complete!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
