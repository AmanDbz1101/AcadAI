"""
Test script for section refinement functionality.
"""

from src.models import SectionMetadata
from src.llm_inference import SectionRefinementEngine


def test_section_refinement():
    """Test the section refinement with sample data."""
    
    # Sample section metadata with false positives
    sample_sections = [
        SectionMetadata(original_name="Abstract", normalized_name=None, page_start=1),
        SectionMetadata(original_name="MemGPT: Towards LLMs as Operating Systems", normalized_name=None, page_start=1),
        SectionMetadata(original_name="1. Introduction", normalized_name="Introduction", page_start=1),
        SectionMetadata(original_name="X", normalized_name=None, page_start=2),
        SectionMetadata(original_name="Background", normalized_name="Background", page_start=2),
        SectionMetadata(original_name="RAG", normalized_name=None, page_start=2),
        SectionMetadata(original_name="2. Methods", normalized_name="Methods", page_start=3),
        SectionMetadata(original_name="2.1 Models", normalized_name="Models", page_start=3),
        SectionMetadata(original_name="2.2 Retriever: DPR", normalized_name=None, page_start=4),
        SectionMetadata(original_name="3. Experiments", normalized_name="Experiments", page_start=5),
        SectionMetadata(original_name="4. Results", normalized_name="Results", page_start=7),
        SectionMetadata(original_name="5. Related Work", normalized_name="Related Work", page_start=9),
        SectionMetadata(original_name="6. Discussion", normalized_name="Discussion", page_start=10),
        SectionMetadata(original_name="References", normalized_name="References", page_start=11),
    ]
    
    print("Original sections (with false positives):")
    print("-" * 60)
    for i, section in enumerate(sample_sections, 1):
        print(f"{i:2d}. {section.original_name} (page {section.page_start})")
    
    print("\n" + "=" * 60)
    print("Refining sections using LLM...")
    print("=" * 60 + "\n")
    
    # Create refinement engine
    engine = SectionRefinementEngine()
    
    # Refine sections
    refined_sections = engine.refine_sections(sample_sections)
    
    print("Refined sections (false positives removed):")
    print("-" * 60)
    for i, section in enumerate(refined_sections, 1):
        print(f"{i:2d}. {section.original_name} (page {section.page_start})")
    
    print("\n" + "=" * 60)
    print(f"Summary: Removed {len(sample_sections) - len(refined_sections)} false positives")
    print(f"Original count: {len(sample_sections)}")
    print(f"Refined count: {len(refined_sections)}")
    print("=" * 60)


if __name__ == "__main__":
    test_section_refinement()
