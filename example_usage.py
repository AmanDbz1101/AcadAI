"""
Example usage of the Research Paper Metadata Extractor.

This script demonstrates how to use the extractor in your code.
"""

import os
from pathlib import Path
from src.extractor import extract_paper_metadata
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def example_basic_usage():
    """Basic usage example."""
    print("Example 1: Basic Usage")
    print("-" * 50)
    
    # Path to your PDF
    pdf_path = "input/MemGPT.pdf"
    
    # Extract metadata
    metadata = extract_paper_metadata(pdf_path)
    
    # Access the results
    print(f"Title: {metadata.title}")
    print(f"Paper Type: {metadata.inference.paper_type}")
    print(f"Difficulty: {metadata.inference.difficulty}")
    print(f"Number of sections: {len(metadata.sections)}")
    print()


def example_detailed_analysis():
    """Detailed analysis example."""
    print("Example 2: Detailed Section Analysis")
    print("-" * 50)
    
    pdf_path = "input/MemGPT.pdf"
    metadata = extract_paper_metadata(pdf_path)
    
    # Analyze sections
    print("Section Structure:")
    for section in metadata.sections:
        print(f"  • {section.original_name}")
        if section.normalized_name:
            print(f"    → Normalized as: {section.normalized_name}")
        print(f"    → Starts on page {section.page_start}")
    print()


def example_batch_processing():
    """Batch processing example."""
    print("Example 3: Batch Processing")
    print("-" * 50)
    
    input_dir = Path("input")
    pdf_files = list(input_dir.glob("*.pdf"))
    
    results = []
    for pdf_file in pdf_files:
        try:
            print(f"Processing: {pdf_file.name}")
            metadata = extract_paper_metadata(str(pdf_file))
            results.append({
                "filename": pdf_file.name,
                "title": metadata.title,
                "type": metadata.inference.paper_type,
                "difficulty": metadata.inference.difficulty
            })
        except Exception as e:
            print(f"  Error: {e}")
    
    print(f"\nProcessed {len(results)} papers successfully")
    print()


def example_export_to_json():
    """Export metadata to JSON."""
    print("Example 4: Export to JSON")
    print("-" * 50)
    
    import json
    
    pdf_path = "input/MemGPT.pdf"
    metadata = extract_paper_metadata(pdf_path)
    
    # Convert to dict
    metadata_dict = metadata.model_dump()
    
    # Save to JSON
    output_path = "output/metadata.json"
    with open(output_path, "w") as f:
        json.dump(metadata_dict, f, indent=2)
    
    print(f"Metadata saved to: {output_path}")
    print()


def example_error_handling():
    """Example with error handling."""
    print("Example 5: Error Handling")
    print("-" * 50)
    
    from pathlib import Path
    
    pdf_path = "input/nonexistent.pdf"
    
    try:
        metadata = extract_paper_metadata(pdf_path)
    except FileNotFoundError:
        print(f"Error: PDF file not found at {pdf_path}")
    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    print()


if __name__ == "__main__":
    # Run examples
    print("=" * 80)
    print("RESEARCH PAPER METADATA EXTRACTOR - USAGE EXAMPLES")
    print("=" * 80)
    print()
    
    # Make sure to set GROQ_API_KEY in your .env file
    if not os.getenv("GROQ_API_KEY"):
        print("⚠️  Warning: GROQ_API_KEY not set in .env file")
        print("   Add it to your .env file: GROQ_API_KEY='your_key_here'")
        print()
    
    # Run examples (uncomment the ones you want to try)
    # example_basic_usage()
    # example_detailed_analysis()
    # example_batch_processing()
    # example_export_to_json()
    example_error_handling()
    
    print("=" * 80)
