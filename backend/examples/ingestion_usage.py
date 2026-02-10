"""
Example usage of the PDF Ingestion module.

Demonstrates different ways to use the ingestion pipeline.
"""

from pathlib import Path
import sys

# Add project root to path (two levels up from examples/)
examples_dir = Path(__file__).parent
backend_dir = examples_dir.parent
project_root = backend_dir.parent
sys.path.insert(0, str(project_root))

from backend.pipelines import IngestPipeline
from backend.services import IngestionService
from backend.app.ingestion import PDFValidator, PDFLoader


def example_1_basic_ingestion():
    """Example 1: Basic PDF ingestion."""
    print("=" * 60)
    print("Example 1: Basic PDF Ingestion")
    print("=" * 60)
    
    # Initialize pipeline
    pipeline = IngestPipeline()
    
    # Process a PDF
    pdf_path = Path("Research Papers/your_paper.pdf")
    
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return
    
    document = pipeline.process(pdf_path)
    
    # Display results
    print(f"\n✓ Document ID: {document.document_id}")
    print(f"✓ Pages: {document.page_count}")
    print(f"✓ Total words: {document.total_word_count:,}")
    print(f"✓ Total chars: {document.total_char_count:,}")
    print(f"✓ OCR applied: {document.ocr_metadata.was_ocr_applied if document.ocr_metadata else False}")
    print(f"✓ Processing time: {document.processing_time_seconds:.2f}s")
    
    # Show first page preview
    first_page = document.pages[0]
    print(f"\n📄 First Page Preview:")
    print(first_page.text[:200] + "...")


def example_2_validation_only():
    """Example 2: Validate PDF without processing."""
    print("\n" + "=" * 60)
    print("Example 2: PDF Validation Only")
    print("=" * 60)
    
    validator = PDFValidator(
        max_file_size_mb=50,
        min_pages=1,
    )
    
    pdf_path = Path("Research Papers/your_paper.pdf")
    
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return
    
    result = validator.validate(pdf_path)
    
    if result.is_valid:
        print(f"\n✓ Valid PDF")
        print(f"  Pages: {result.page_count}")
        print(f"  Size: {result.file_size_bytes / 1024:.1f} KB")
        print(f"  Hash: {result.pdf_hash[:16]}...")
    else:
        print(f"\n✗ Invalid PDF")
        for error in result.errors:
            print(f"  - {error.error_type}: {error.message}")


def example_3_ocr_detection():
    """Example 3: Detect if PDF needs OCR."""
    print("\n" + "=" * 60)
    print("Example 3: OCR Detection")
    print("=" * 60)
    
    loader = PDFLoader()
    
    pdf_path = Path("Research Papers/your_paper.pdf")
    
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return
    
    # Load without OCR
    result = loader.load(pdf_path)
    
    # Analyze readability
    readability = loader.detect_readability(result['pages'])
    
    print(f"\n📊 Readability Analysis:")
    print(f"  Machine readable: {readability['is_machine_readable']}")
    print(f"  Avg text density: {readability['average_text_density']:.1f} chars/page")
    print(f"  Pages needing OCR: {readability['pages_needing_ocr']}")
    print(f"  Recommendation: {readability['recommendation']}")


def example_4_with_service():
    """Example 4: Using the service layer with caching."""
    print("\n" + "=" * 60)
    print("Example 4: Service Layer with Caching")
    print("=" * 60)
    
    # Initialize service
    service = IngestionService(
        cache_dir=Path("cache"),
        enable_deduplication=True,
    )
    
    # Progress callback
    def progress(message: str, pct: float):
        print(f"  [{pct:5.1f}%] {message}")
    
    pdf_path = Path("Research Papers/your_paper.pdf")
    
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return
    
    # Check for duplicates
    duplicate_id = service.is_duplicate(pdf_path)
    if duplicate_id:
        print(f"\n⚠️  Duplicate detected: {duplicate_id}")
        return
    
    # Process with progress tracking
    print(f"\n📥 Processing: {pdf_path.name}")
    document = service.ingest(
        pdf_path=pdf_path,
        progress_callback=progress,
    )
    
    print(f"\n✓ Complete: {document.document_id}")
    
    # Show stats
    stats = service.get_stats()
    print(f"\n📊 Service Stats:")
    print(f"  Processed documents: {stats['processed_documents']}")
    print(f"  Cache enabled: {stats['cache_enabled']}")


def example_5_batch_processing():
    """Example 5: Batch process multiple PDFs."""
    print("\n" + "=" * 60)
    print("Example 5: Batch Processing")
    print("=" * 60)
    
    pipeline = IngestPipeline()
    
    # Find all PDFs in directory
    pdf_dir = Path("Research Papers")
    pdf_files = list(pdf_dir.glob("*.pdf"))[:3]  # Process first 3
    
    if not pdf_files:
        print(f"No PDFs found in: {pdf_dir}")
        return
    
    print(f"\n📥 Processing {len(pdf_files)} PDFs...")
    
    results = pipeline.process_batch(
        pdf_paths=pdf_files,
        continue_on_error=True,
    )
    
    print(f"\n✓ Batch Complete:")
    print(f"  Successful: {len(results['successful'])}")
    print(f"  Failed: {len(results['failed'])}")
    
    # Show successful documents
    for doc in results['successful']:
        print(f"\n  ✓ {doc.pdf_path.name}")
        print(f"     Pages: {doc.page_count}, Time: {doc.processing_time_seconds:.1f}s")
    
    # Show failures
    for path, error in results['failed']:
        print(f"\n  ✗ {path.name}")
        print(f"     Error: {error}")


def example_6_page_access():
    """Example 6: Accessing individual pages and ranges."""
    print("\n" + "=" * 60)
    print("Example 6: Page Access")
    print("=" * 60)
    
    pipeline = IngestPipeline()
    
    pdf_path = Path("Research Papers/your_paper.pdf")
    
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return
    
    document = pipeline.process(pdf_path)
    
    # Access specific page
    page_3 = document.get_page(3)
    if page_3:
        print(f"\n📄 Page 3:")
        print(f"  Words: {page_3.word_count}")
        print(f"  Has tables: {page_3.has_tables}")
        print(f"  Has formulas: {page_3.has_formulas}")
        print(f"  Preview: {page_3.text[:150]}...")
    
    # Get text range
    intro_text = document.get_text_range(1, 3)
    print(f"\n📚 Pages 1-3 combined:")
    print(f"  Length: {len(intro_text)} chars")
    print(f"  Preview: {intro_text[:200]}...")


def main():
    """Run all examples."""
    print("\n🚀 PDF Ingestion Module - Usage Examples\n")
    
    examples = [
        example_1_basic_ingestion,
        example_2_validation_only,
        example_3_ocr_detection,
        example_4_with_service,
        example_5_batch_processing,
        example_6_page_access,
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"\n❌ Error in {example.__name__}: {str(e)}")
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
