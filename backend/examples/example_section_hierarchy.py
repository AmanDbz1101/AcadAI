"""
Example: Section Hierarchy Detection

Demonstrates how to use the Section Hierarchy Detection module
to extract and navigate the structure of a research paper.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.pipelines import IngestPipeline, MetadataExtractionPipeline, SectionHierarchyPipeline
from backend.models import SectionHierarchy


def print_section_tree(hierarchy: SectionHierarchy, section_id: str = None, indent: int = 0):
    """Pretty-print section tree structure."""
    if section_id is None:
        # Print root sections
        for root_id in hierarchy.root_sections:
            print_section_tree(hierarchy, root_id, indent)
    else:
        section = hierarchy.get_section(section_id)
        if not section:
            return
        
        # Print current section
        prefix = "  " * indent
        numbering = f"{section.numbering} " if section.numbering else ""
        print(f"{prefix}{numbering}{section.title} (Level {section.level}, Page {section.page_start})")
        
        # Print children
        for child_id in section.child_section_ids:
            print_section_tree(hierarchy, child_id, indent + 1)


def main():
    """Run example section hierarchy detection."""
    
    # Check if PDF path provided
    if len(sys.argv) < 2:
        print("Usage: python example_section_hierarchy.py <path_to_pdf>")
        print("\nThis example will:")
        print("1. Ingest the PDF")
        print("2. Extract metadata")
        print("3. Detect section hierarchy")
        print("4. Display the hierarchical structure")
        sys.exit(1)
    
    pdf_path = Path(sys.argv[1])
    
    if not pdf_path.exists():
        print(f"Error: PDF file not found at {pdf_path}")
        sys.exit(1)
    
    print("=" * 80)
    print("Section Hierarchy Detection Example")
    print("=" * 80)
    print(f"\nProcessing: {pdf_path.name}\n")
    
    # Step 1: Ingest PDF
    print("Step 1: Ingesting PDF...")
    ingest_pipeline = IngestPipeline()
    validated_doc = ingest_pipeline.process(pdf_path)
    print(f"✓ Ingested {validated_doc.page_count} pages")
    
    # Step 2: Extract metadata
    print("\nStep 2: Extracting metadata...")
    metadata_pipeline = MetadataExtractionPipeline()
    processed_doc = metadata_pipeline.process(validated_doc)
    print(f"✓ Extracted metadata")
    print(f"  Title: {processed_doc.metadata.title}")
    print(f"  Sections found: {len(processed_doc.metadata.sections)}")
    
    # Step 3: Detect section hierarchy
    print("\nStep 3: Detecting section hierarchy...")
    hierarchy_pipeline = SectionHierarchyPipeline()
    result = hierarchy_pipeline.process_from_processed_document(processed_doc, validated_doc)
    
    hierarchy = result.hierarchy
    print(f"✓ Detected hierarchy in {result.processing_time_seconds:.2f}s")
    print(f"  Total sections: {hierarchy.total_sections}")
    print(f"  Maximum depth: {hierarchy.max_depth}")
    print(f"  Confidence: {hierarchy.confidence_score:.2f}")
    
    if result.warnings:
        print("\n  Warnings:")
        for warning in result.warnings:
            print(f"    - {warning}")
    
    # Step 4: Display section tree
    print("\n" + "=" * 80)
    print("Section Hierarchy Tree")
    print("=" * 80 + "\n")
    
    print_section_tree(hierarchy)
    
    # Step 5: Demonstrate navigation capabilities
    print("\n" + "=" * 80)
    print("Navigation Examples")
    print("=" * 80 + "\n")
    
    # Find all level-1 sections
    level1_sections = hierarchy.get_sections_by_level(1)
    print(f"Level-1 sections ({len(level1_sections)}):")
    for section in level1_sections:
        print(f"  - {section.title} (Page {section.page_start})")
    
    # Find sections by keyword
    print("\nSections containing 'method':")
    method_sections = hierarchy.find_sections_by_title("method", case_sensitive=False)
    for section in method_sections:
        print(f"  - {section.full_path} (Page {section.page_start})")
    
    # Show parent-child relationships
    if level1_sections:
        first_section = level1_sections[0]
        children = hierarchy.get_children(first_section.section_id)
        if children:
            print(f"\nChildren of '{first_section.title}':")
            for child in children:
                print(f"  - {child.title} (Level {child.level})")
    
    # Step 6: Save hierarchy to file
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{validated_doc.document_id}_hierarchy.json"
    
    print(f"\nSaving hierarchy to {output_file}...")
    hierarchy_pipeline.save_hierarchy(hierarchy, output_file)
    print("✓ Saved")
    
    print("\n" + "=" * 80)
    print("Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
