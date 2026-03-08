"""Quick test of Docling's formula detection capabilities."""

import sys
sys.path.append('..')

from docling.document_converter import DocumentConverter
from pathlib import Path
from collections import Counter

def test_formula_detection(pdf_path: str):
    """Test formula detection on a single PDF."""
    print(f"\n{'='*60}")
    print(f"Testing: {Path(pdf_path).name}")
    print('='*60)
    
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    doc = result.document
    
    # Get page count
    page_count = len(doc.pages) if hasattr(doc, 'pages') else 1
    
    # Count all item types
    item_types = Counter()
    formula_count = 0
    formulas = []
    
    for item, level in doc.iterate_items():
        item_types[item.label] += 1
        
        if item.label in ["formula", "equation"]:
            formula_count += 1
            text = getattr(item, 'text', '')
            page = getattr(item.prov[0], "page_no", -1) + 1 if hasattr(item, 'prov') and item.prov else 0
            
            formulas.append({
                'text': text[:100],  # First 100 chars
                'page': page
            })
    
    print(f"\nDocument Statistics:")
    print(f"  Pages: {page_count}")
    print(f"  Total Items: {sum(item_types.values())}")
    
    print(f"\nItem Types Found:")
    for item_type, count in sorted(item_types.items(), key=lambda x: -x[1]):
        print(f"  {item_type:20} : {count:3}")
    
    print(f"\n{'='*60}")
    print(f"FORMULAS: {formula_count}")
    print(f"Formula Density: {formula_count / page_count:.2f} formulas/page")
    print('='*60)
    
    if formulas:
        print(f"\nFirst 3 formulas:")
        for i, formula in enumerate(formulas[:3], 1):
            print(f"\n  Formula {i} (Page {formula['page']}):")
            print(f"    {formula['text']}")
    else:
        print("\n⚠️  WARNING: NO FORMULAS DETECTED BY DOCLING!")
        print("    This may indicate:")
        print("    1. PDF has no formulas")
        print("    2. Docling is not detecting them correctly")
        print("    3. Need to use pix2text-mfr fallback")
    
    return {
        'pages': page_count,
        'formulas': formula_count,
        'item_types': dict(item_types),
        'formulas_per_page': formula_count / page_count if page_count > 0 else 0
    }


if __name__ == "__main__":
    # Test multiple PDFs
    test_paths = []
    
    # Check for sample PDFs
    input_dir = Path("../input")
    if input_dir.exists():
        test_paths.extend(list(input_dir.glob("*.pdf"))[:2])
    
    research_dir = Path("../Research Papers")
    if research_dir.exists():
        test_paths.extend(list(research_dir.glob("*.pdf"))[:2])
    
    if not test_paths:
        print("No PDFs found. Place PDFs in input/ or Research Papers/ folder.")
        sys.exit(1)
    
    print(f"\nTesting {len(test_paths)} PDFs for formula detection...")
    
    results = []
    for pdf_path in test_paths:
        try:
            result = test_formula_detection(str(pdf_path))
            results.append({
                'file': pdf_path.name,
                **result
            })
        except Exception as e:
            print(f"\n✗ Error processing {pdf_path.name}: {e}")
    
    # Summary
    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    
    for r in results:
        print(f"\n{r['file']}")
        print(f"  Formulas: {r['formulas']:3} | Pages: {r['pages']:3} | Density: {r['formulas_per_page']:.2f}")
        
        # Classification
        is_math_heavy = r['formulas_per_page'] >= 1.5 or r['formulas'] >= 10
        print(f"  Math-Heavy: {'YES' if is_math_heavy else 'NO'}")
    
    # Recommendation
    total_formulas = sum(r['formulas'] for r in results)
    avg_density = sum(r['formulas_per_page'] for r in results) / len(results) if results else 0
    
    print(f"\n{'='*60}")
    print("RECOMMENDATION")
    print('='*60)
    
    if avg_density > 0.5:
        print("✓ Docling formula detection appears to be working")
        print(f"  Average density: {avg_density:.2f} formulas/page")
        print("  → Use Docling for formula counting")
    else:
        print("⚠️  Low formula detection rate")
        print(f"  Average density: {avg_density:.2f} formulas/page")
        print("  → Consider implementing pix2text-mfr fallback")
        print("  → Extract formula regions manually and count them")
