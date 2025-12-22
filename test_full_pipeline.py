"""
Quick test of the full extraction pipeline with section refinement.
"""

from src.extractor import extract_paper_metadata


def test_full_pipeline():
    """Test the full extraction pipeline."""
    
    print("=" * 80)
    print("Testing Full Extraction Pipeline with Section Refinement")
    print("=" * 80)
    
    pdf_path = "input/Gated Attention.pdf"
    
    print(f"\nExtracting metadata from: {pdf_path}")
    print("-" * 80)
    
    # Extract metadata
    metadata = extract_paper_metadata(pdf_path)
    
    # Display results
    print("\n📄 TITLE:")
    print(f"   {metadata.title}")
    
    print("\n📝 ABSTRACT (first 200 chars):")
    print(f"   {metadata.abstract[:200]}...")
    
    print("\n📊 PAPER PROPERTIES:")
    print(f"   Type: {metadata.inference.paper_type}")
    print(f"   Difficulty: {metadata.inference.difficulty}")
    print(f"   Math Heavy: {metadata.inference.math_heavy}")
    
    print("\n📑 REFINED SECTION STRUCTURE:")
    for i, section in enumerate(metadata.sections, 1):
        normalized = f" → {section.normalized_name}" if section.normalized_name else ""
        print(f"   {i:2d}. {section.original_name}{normalized} (page {section.page_start})")
    
    print("\n" + "=" * 80)
    print(f"✅ Successfully extracted metadata with {len(metadata.sections)} sections")
    print("=" * 80)


if __name__ == "__main__":
    test_full_pipeline()
