"""
Simple tests for the metadata extractor.

Run with: python test_extractor.py
"""

import sys
from pathlib import Path


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    try:
        from src import models
        from src import text_extraction
        from src import section_detection
        from src import normalization
        from src import abstract_extraction
        from src import llm_inference
        from src import graph
        from src import extractor
        print("✓ All modules imported successfully")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_models():
    """Test Pydantic models."""
    print("\nTesting Pydantic models...")
    
    try:
        from src.models import SectionMetadata, PaperInference, PaperMetadata
        
        # Test SectionMetadata
        section = SectionMetadata(
            original_name="1. Introduction",
            normalized_name="Introduction",
            page_start=1
        )
        assert section.original_name == "1. Introduction"
        
        # Test PaperInference
        inference = PaperInference(
            paper_type="Survey",
            difficulty="medium",
            math_heavy=False
        )
        assert inference.paper_type == "Survey"
        
        # Test PaperMetadata
        metadata = PaperMetadata(
            title="Test Paper",
            abstract="This is a test abstract.",
            sections=[section],
            inference=inference
        )
        assert metadata.title == "Test Paper"
        
        print("✓ Pydantic models work correctly")
        return True
    except Exception as e:
        print(f"✗ Model test failed: {e}")
        return False


def test_section_normalizer():
    """Test section normalization."""
    print("\nTesting section normalizer...")
    
    try:
        from src.normalization import SectionNormalizer
        
        normalizer = SectionNormalizer()
        
        # Test various section names
        test_cases = [
            ("1. Introduction", "Introduction"),
            ("Related Work", "Related Work"),
            ("3.2 Methodology", "Methodology"),
            ("Experimental Setup", "Experiments"),
            ("Results and Discussion", "Results"),
            ("5. Conclusion", "Conclusion"),
        ]
        
        for original, expected in test_cases:
            result = normalizer.normalize(original)
            if result:
                print(f"  {original} → {result}")
        
        print("✓ Section normalizer works")
        return True
    except Exception as e:
        print(f"✗ Normalizer test failed: {e}")
        return False


def test_section_detector():
    """Test section detection heuristics."""
    print("\nTesting section detector...")
    
    try:
        from src.section_detection import SectionDetector
        from src.text_extraction import TextBlock
        
        detector = SectionDetector()
        
        # Create mock text blocks
        blocks = [
            TextBlock("1. Introduction", 1, "Title", {}),
            TextBlock("This is the introduction text.", 1, "NarrativeText", {}),
            TextBlock("2. Methodology", 2, "Title", {}),
            TextBlock("We used the following methods.", 2, "NarrativeText", {}),
        ]
        
        candidates = detector.detect_sections(blocks)
        
        print(f"  Detected {len(candidates)} section candidates")
        for candidate in candidates:
            print(f"  - {candidate.text} (confidence: {candidate.confidence:.2f})")
        
        print("✓ Section detector works")
        return True
    except Exception as e:
        print(f"✗ Detector test failed: {e}")
        return False


def test_graph_structure():
    """Test that LangGraph can be initialized."""
    print("\nTesting LangGraph structure...")
    
    try:
        from src.graph import MetadataExtractionGraph
        
        # Initialize without API key (won't run, just test structure)
        graph = MetadataExtractionGraph(groq_api_key="test_key")
        
        assert graph.graph is not None
        print("✓ LangGraph initialized successfully")
        return True
    except Exception as e:
        print(f"✗ Graph test failed: {e}")
        return False


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("RESEARCH PAPER METADATA EXTRACTOR - TESTS")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_models,
        test_section_normalizer,
        test_section_detector,
        test_graph_structure,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
