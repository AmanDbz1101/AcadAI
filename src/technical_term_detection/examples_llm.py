"""
Example script demonstrating the LLM-based term extractor.

This script shows how to use the term extractor with different types of paragraphs
from various domains.
"""

import os
import json
from term_extractor_llm import (
    LLMTermExtractor,
    LLMTermDefinitionFinder,
    LLMTermExtractorPipeline
)


def example_1_basic_extraction():
    """Example 1: Basic term extraction without definitions."""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Basic Term Extraction")
    print("=" * 80)
    
    extractor = LLMTermExtractor(model="gpt-4o-mini")
    
    paragraph = """
    Machine learning algorithms learn patterns from data without being explicitly 
    programmed. Supervised learning uses labeled datasets, while unsupervised 
    learning discovers hidden patterns in unlabeled data. Reinforcement learning 
    involves agents learning through trial and error.
    """
    
    print(f"\nParagraph:\n{paragraph.strip()}")
    print("\nExtracting technical terms...")
    
    terms = extractor.extract_terms(paragraph, domain="machine learning")
    
    print(f"\nExtracted {len(terms)} terms:")
    for i, term in enumerate(terms, 1):
        print(f"  {i}. {term}")


def example_2_terms_with_context():
    """Example 2: Extract terms with their usage context."""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Terms with Context")
    print("=" * 80)
    
    extractor = LLMTermExtractor(model="gpt-4o-mini")
    
    paragraph = """
    CRISPR-Cas9 is a revolutionary gene-editing technology that allows scientists 
    to precisely modify DNA sequences. The system uses guide RNAs to target 
    specific genomic locations, where the Cas9 nuclease creates double-strand 
    breaks. This enables targeted gene knockout or insertion through homology-directed 
    repair mechanisms.
    """
    
    print(f"\nParagraph:\n{paragraph.strip()}")
    print("\nExtracting terms with context...")
    
    terms_with_context = extractor.extract_terms_with_context(paragraph, domain="biology")
    
    print(f"\nExtracted {len(terms_with_context)} terms:")
    for i, item in enumerate(terms_with_context, 1):
        print(f"\n  {i}. Term: {item['term']}")
        print(f"     Context: {item['context']}")


def example_3_find_definitions():
    """Example 3: Find definitions for specific terms."""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Finding Definitions")
    print("=" * 80)
    
    finder = LLMTermDefinitionFinder(model="gpt-4o-mini")
    
    terms = ["quantum entanglement", "superposition", "wave function"]
    
    print(f"\nFinding definitions for: {', '.join(terms)}")
    print(f"Domain: physics\n")
    
    definitions = finder.find_definitions_batch(terms, domain="physics")
    
    for def_info in definitions:
        print(f"\nTerm: {def_info['term']}")
        print(f"Definition: {def_info['definition']}")
        if def_info.get('synonyms'):
            print(f"Synonyms: {', '.join(def_info['synonyms'])}")
        if def_info.get('related_terms'):
            print(f"Related: {', '.join(def_info['related_terms'][:3])}")


def example_4_complete_pipeline():
    """Example 4: Complete pipeline with extraction and definitions."""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Complete Pipeline")
    print("=" * 80)
    
    pipeline = LLMTermExtractorPipeline(model="gpt-4o-mini")
    
    paragraph = """
    Blockchain technology provides a decentralized ledger system using cryptographic 
    hashing and consensus mechanisms. Smart contracts enable automated execution of 
    agreements through distributed nodes. The proof-of-work algorithm ensures 
    network security through computational puzzles, while proof-of-stake offers 
    a more energy-efficient alternative.
    """
    
    print(f"\nParagraph:\n{paragraph.strip()}")
    print("\nProcessing with complete pipeline...")
    
    result = pipeline.process_paragraph_with_context(
        paragraph, 
        domain="computer science"
    )
    
    print(f"\n\nRESULTS:")
    print(f"Total terms found: {result['total_terms']}\n")
    
    for i, term_info in enumerate(result['enriched_terms'], 1):
        print(f"\n{i}. {term_info['term']}")
        print(f"   Context: {term_info['context']}")
        print(f"   Definition: {term_info['definition'][:150]}...")
        if term_info.get('synonyms'):
            print(f"   Synonyms: {', '.join(term_info['synonyms'][:3])}")


def example_5_custom_domain():
    """Example 5: Process paragraph from a specific domain."""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Custom Domain (Medicine)")
    print("=" * 80)
    
    pipeline = LLMTermExtractorPipeline(model="gpt-4o-mini")
    
    paragraph = """
    Immunotherapy harnesses the body's immune system to fight cancer. Checkpoint 
    inhibitors block proteins that prevent T cells from attacking cancer cells. 
    CAR T-cell therapy genetically engineers a patient's lymphocytes to recognize 
    tumor antigens, while monoclonal antibodies target specific proteins on 
    cancer cell surfaces.
    """
    
    print(f"\nParagraph:\n{paragraph.strip()}")
    print("\nProcessing medical text...")
    
    result = pipeline.process_paragraph_with_context(
        paragraph, 
        domain="medicine"
    )
    
    # Save to JSON
    output_file = "medical_terms_example.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n\nExtracted {result['total_terms']} medical terms")
    print(f"Results saved to: {output_file}")
    
    print("\n\nSample terms:")
    for term_info in result['enriched_terms'][:3]:
        print(f"\n• {term_info['term']}")
        print(f"  {term_info['definition'][:120]}...")


def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print(" LLM-Based Technical Term Extraction - Examples")
    print("=" * 80)
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ Error: OPENAI_API_KEY environment variable not set.")
        print("\nPlease set it with:")
        print("  export OPENAI_API_KEY='your-api-key-here'")
        print("\nOr create a .env file with:")
        print("  OPENAI_API_KEY=your-api-key-here")
        return
    
    print("\n✅ OpenAI API key found")
    print("\nRunning examples...\n")
    
    try:
        # Run examples
        example_1_basic_extraction()
        
        input("\n\nPress Enter to continue to Example 2...")
        example_2_terms_with_context()
        
        input("\n\nPress Enter to continue to Example 3...")
        example_3_find_definitions()
        
        input("\n\nPress Enter to continue to Example 4...")
        example_4_complete_pipeline()
        
        input("\n\nPress Enter to continue to Example 5...")
        example_5_custom_domain()
        
        print("\n" + "=" * 80)
        print(" All examples completed successfully!")
        print("=" * 80)
        print("\nTip: Modify the paragraphs and domains in this script to test")
        print("with your own content.\n")
        
    except KeyboardInterrupt:
        print("\n\nExamples interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        print("\nPlease check:")
        print("1. Your API key is valid")
        print("2. You have internet connectivity")
        print("3. Your OpenAI account has available credits")


if __name__ == "__main__":
    main()
