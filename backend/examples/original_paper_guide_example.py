"""
Original Paper Guide Example - Research Paper Assistant
=======================================================
Demonstrates how to generate a Three-Pass Method reading guide
for research papers (APPLIED, THEORETICAL, SURVEY categories).

When you run this on a research paper, it will:
1. Extract metadata from the PDF
2. Categorize the paper (APPLIED, THEORETICAL, or SURVEY)
3. Generate a detailed reading guide
4. Save the guide to output/<document_id>_guide.json

Usage:
    python backend/examples/original_paper_guide_example.py
"""

import sys
from pathlib import Path

# Add project root to path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_BACKEND_DIR))

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from backend.run import PaperAnalysisPipeline


def example_original_paper_guide():
    """
    Example: Generate a reading guide for a research paper.

    The guide will be generated for any categorized paper when:
    - The paper category is APPLIED, THEORETICAL, or SURVEY
    - No query is provided (guide mode, not Q&A mode)
    """
    print("\n" + "=" * 70)
    print("  EXAMPLE: Original Research Paper Reading Guide")
    print("=" * 70 + "\n")
    
    # Use first available PDF from the input folder
    input_dir = Path("input")
    available_pdfs = list(input_dir.glob("*.pdf")) if input_dir.exists() else []
    if not available_pdfs:
        print("⚠️  No PDF files found in the input/ folder.")
        print("   Please add a PDF research paper to the input/ directory.")
        return
    pdf_path = str(available_pdfs[0])
    print(f"📄 Using PDF: {pdf_path}")
    
    # Create pipeline
    pipeline = PaperAnalysisPipeline()
    
    # Run pipeline without query (this triggers guide generation for all recognized categories)
    result = pipeline.run(
        pdf_path=pdf_path,
        force_ocr=False,
        query=None,  # No query = guide mode
        summarize=False
    )
    
    # Display results
    print(f"✅ Document ID: {result.get('document_id')}")
    print(f"📄 Title: {result.get('title', 'N/A')[:80]}")
    print(f"📚 Category: {result.get('category', 'N/A')}")
    print(f"🎯 Confidence: {result.get('confidence', 'N/A')}")
    
    # Check if guide was generated
    if result.get('reading_guide'):
        print(f"\n📖 Reading Guide Generated!")
        print(f"📁 Guide File: {result.get('guide_file_path')}")
        
        guide = result['reading_guide']
        print(f"\n📋 Guide Details:")
        print(f"   Method: {guide.get('reading_strategy', {}).get('method', 'N/A')}")
        print(f"   Paper Type: {guide.get('reading_strategy', {}).get('paper_type', 'N/A')}")
        print(f"   Estimated Time: {guide.get('reading_strategy', {}).get('estimated_total_time', 'N/A')}")
        
        # Show Pass 1 steps
        pass1 = guide.get('pass1_quick_scan', {})
        if pass1:
            print(f"\n🔍 Pass 1 - Quick Scan:")
            print(f"   Goal: {pass1.get('goal', 'N/A')}")
            print(f"   Time: {pass1.get('estimated_time', 'N/A')}")
            print(f"   Steps: {len(pass1.get('steps', []))}")
        
        # Show Pass 2 steps
        pass2 = guide.get('pass2_method_understanding', {})
        if pass2:
            print(f"\n🧪 Pass 2 - Method Understanding:")
            print(f"   Goal: {pass2.get('goal', 'N/A')}")
            print(f"   Time: {pass2.get('estimated_time', 'N/A')}")
            print(f"   Steps: {len(pass2.get('steps', []))}")
        
        # Show Pass 3 steps
        pass3 = guide.get('pass3_deep_analysis', {})
        if pass3:
            print(f"\n🔬 Pass 3 - Deep Analysis:")
            print(f"   Goal: {pass3.get('goal', 'N/A')}")
            print(f"   Time: {pass3.get('estimated_time', 'N/A')}")
            print(f"   Steps: {len(pass3.get('steps', []))}")
        
        print(f"\n✅ Guide saved to: {result.get('guide_file_path')}")
        print(f"\n💡 Tip: Open the JSON file to see the complete step-by-step guide!")
        
    elif result.get('category') not in ('APPLIED', 'THEORETICAL', 'SURVEY'):
        print(f"\n⚠️  Reading guide not generated.")
        print(f"   Reason: Paper category is '{result.get('category')}', which is not a known category.")
        print(f"   Guide generation is supported for APPLIED, THEORETICAL, and SURVEY papers.")
        
        if result.get('summary'):
            print(f"\n📝 Summary generated instead:")
            print("=" * 70)
            print(result['summary'][:500] + "..." if len(result.get('summary', '')) > 500 else result.get('summary'))
            
    else:
        print(f"\n⚠️  Reading guide not generated.")
        print(f"   Check errors: {result.get('errors', [])}")
    
    # Show any errors
    if result.get('errors'):
        print(f"\n⚠️  Errors encountered:")
        for error in result['errors']:
            print(f"   - {error}")
    
    print("\n" + "-" * 70)


def example_with_existing_paper():
    """
    Example using an existing paper from the output folder.

    This demonstrates that the guide is generated when:
    - Category is APPLIED, THEORETICAL, or SURVEY
    - No query is provided
    """
    print("\n" + "=" * 70)
    print("  EXAMPLE: Using Existing Sample Paper")
    print("=" * 70 + "\n")
    
    # Check for existing papers in the input folder
    input_dir = Path("input")
    if input_dir.exists():
        pdf_files = list(input_dir.glob("*.pdf"))
        if pdf_files:
            pdf_path = str(pdf_files[0])
            print(f"📄 Found sample paper: {pdf_path}")
            print(f"   Running pipeline to generate reading guide...\n")
            
            pipeline = PaperAnalysisPipeline()
            result = pipeline.run(pdf_path=pdf_path, query=None)
            
            print(f"\n✅ Result:")
            print(f"   Category: {result.get('category')}")
            print(f"   Guide Generated: {'Yes' if result.get('reading_guide') else 'No'}")
            if result.get('guide_file_path'):
                print(f"   Guide File: {result.get('guide_file_path')}")
        else:
            print("⚠️  No PDF files found in input/ folder")
    else:
        print("⚠️  input/ folder not found")


def main():
    """Run examples."""
    print("\n" + "=" * 70)
    print("  ORIGINAL PAPER READING GUIDE EXAMPLES")
    print("=" * 70)
    
    # Check Groq API key
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("\n⚠️  WARNING: GROQ_API_KEY not set in environment")
        print("   Please set it in your .env file or environment variables")
        print("   The guide generation requires Groq API access")
        return
    
    print(f"\n✅ Groq API key found: {groq_key[:10]}...{groq_key[-4:]}")
    
    # Run examples
    example_original_paper_guide()
    
    # Uncomment to test with existing papers (processes same PDF again)
    # example_with_existing_paper()


if __name__ == "__main__":
    main()
