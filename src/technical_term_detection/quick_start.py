#!/usr/bin/env python3
"""
Quick Start Script for LLM-Based Term Extraction

Run this script to quickly test the term extractor with your own text.
"""

import os
from term_extractor_llm import LLMTermExtractorPipeline


def quick_extract():
    """Quick extraction with your own paragraph."""
    
    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Please set OPENAI_API_KEY environment variable")
        print("\nRun: export OPENAI_API_KEY='your-key-here'")
        return
    
    print("=" * 80)
    print(" LLM-Based Term Extractor - Quick Start")
    print("=" * 80)
    
    # Get user input
    print("\n📝 Enter your paragraph (or press Enter for sample):")
    paragraph = input().strip()
    
    if not paragraph:
        paragraph = """
        Transformer models have revolutionized natural language processing through 
        self-attention mechanisms. BERT uses bidirectional encoding, while GPT 
        employs autoregressive generation. These models leverage pre-training on 
        massive corpora followed by fine-tuning for downstream tasks.
        """
        print("\n✓ Using sample paragraph")
    
    print("\n📚 Enter domain (or press Enter for 'general'):")
    print("   Examples: machine learning, biology, physics, medicine, chemistry")
    domain = input().strip() or "general"
    
    # Process
    print(f"\n⚙️  Processing with domain: {domain}")
    print("⏳ Extracting terms and finding definitions...")
    
    try:
        pipeline = LLMTermExtractorPipeline(model="gpt-4o-mini")
        result = pipeline.process_paragraph_with_context(paragraph, domain)
        
        # Display results
        print("\n" + "=" * 80)
        print(f"✅ Found {result['total_terms']} technical terms")
        print("=" * 80 + "\n")
        
        for i, term_info in enumerate(result['enriched_terms'], 1):
            print(f"{i}. 📌 {term_info['term']}")
            print(f"   Context: {term_info['context']}")
            print(f"   Definition: {term_info['definition']}")
            
            if term_info.get('synonyms'):
                print(f"   Synonyms: {', '.join(term_info['synonyms'])}")
            
            if term_info.get('related_terms'):
                print(f"   Related: {', '.join(term_info['related_terms'][:3])}")
            print()
        
        # Save option
        print("\n💾 Save results to file? (y/n):")
        save = input().strip().lower()
        
        if save == 'y':
            import json
            filename = "quick_extraction_results.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"✓ Saved to: {filename}")
        
        print("\n✅ Done!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Check your OPENAI_API_KEY is valid")
        print("2. Ensure you have internet connection")
        print("3. Verify your OpenAI account has credits")


if __name__ == "__main__":
    quick_extract()
