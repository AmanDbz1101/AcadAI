"""
Test script to run metadata extraction on real Qdrant data.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_src import extract_metadata, list_available_documents


def main():
    print("=" * 80)
    print("METADATA EXTRACTION TEST")
    print("=" * 80)
    
    try:
        # Step 1: List available documents
        print("\n1. Listing available documents...")
        docs = list_available_documents()
        print(f"   Found {len(docs)} document(s):")
        for i, doc in enumerate(docs, 1):
            print(f"   {i}. {doc}")
        
        if not docs:
            print("\n❌ No documents found in collection!")
            return
        
        # Step 2: Extract metadata for first document
        test_doc = docs[0]
        print(f"\n2. Extracting metadata for: {test_doc}")
        print("   " + "-" * 60)
        
        metadata = extract_metadata(test_doc)
        
        # Step 3: Display results
        print("\n3. RESULTS:")
        print("   " + "=" * 60)
        print(f"\n   Document ID: {metadata.document_id}")
        print(f"   Title: {metadata.paper_title}")
        print(f"   Abstract: {metadata.abstract[:150]}..." if len(metadata.abstract) > 150 else f"   Abstract: {metadata.abstract}")
        
        print(f"\n   Sections ({len(metadata.sections)}):")
        for i, section in enumerate(metadata.sections[:5], 1):
            print(f"     {i}. {section.original_name}")
            print(f"        Level: {section.level} | Page: {section.page_start}")
            print(f"        Stats: {section.stats.formulas} formulas, {section.stats.tables} tables, {section.stats.figures} figures, {section.stats.text_blocks} text blocks")
        
        if len(metadata.sections) > 5:
            print(f"     ... and {len(metadata.sections) - 5} more sections")
        
        print(f"\n   Global Statistics:")
        print(f"     Total Pages: {metadata.global_stats.total_pages}")
        print(f"     Total Sections: {metadata.global_stats.total_sections}")
        print(f"     Total Formulas: {metadata.global_stats.total_formulas}")
        print(f"     Total Tables: {metadata.global_stats.total_tables}")
        print(f"     Total Figures: {metadata.global_stats.total_figures}")
        print(f"     Total Text Blocks: {metadata.global_stats.total_text_blocks}")
        
        print(f"\n   Inference:")
        print(f"     Paper Type: {metadata.inference.paper_type}")
        print(f"     Math Heavy: {metadata.inference.math_heavy}")
        print(f"     Difficulty: {metadata.inference.difficulty}")
        
        # Step 4: Save to JSON
        print(f"\n4. Saving to JSON...")
        output_file = f"output_{test_doc.replace('/', '_').replace('.pdf', '')}_metadata.json"
        metadata_json = metadata.model_dump_json()
        
        with open(output_file, 'w') as f:
            f.write(metadata_json)
        
        print(f"   ✓ Saved to: {output_file}")
        print(f"   File size: {len(metadata_json)} bytes")
        
        print("\n" + "=" * 80)
        print("✅ TEST COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
