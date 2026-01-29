"""
Integration module for using LLM-based term extraction with the 
Research Paper Assistant project.

This module provides a bridge between the term extractor and the 
metadata extraction pipeline.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional
import json

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from term_extractor_llm import LLMTermExtractorPipeline


class ResearchPaperTermExtractor:
    """
    Integration class for extracting technical terms from research papers.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """
        Initialize the research paper term extractor.
        
        Args:
            api_key: OpenAI API key
            model: Model to use for extraction
        """
        self.pipeline = LLMTermExtractorPipeline(api_key=api_key, model=model)
    
    def extract_from_text(self, text: str, domain: str = "general") -> Dict:
        """
        Extract terms from a text block (e.g., abstract, section).
        
        Args:
            text: The text to process
            domain: The domain/field of the paper
        
        Returns:
            Structured dictionary with terms and definitions
        """
        return self.pipeline.process_paragraph_with_context(text, domain)
    
    def extract_from_paper_sections(
        self, 
        sections: Dict[str, str], 
        domain: str = "general"
    ) -> Dict[str, List[Dict]]:
        """
        Extract terms from multiple sections of a research paper.
        
        Args:
            sections: Dictionary mapping section names to their text
                     e.g., {"abstract": "...", "introduction": "..."}
            domain: The domain/field of the paper
        
        Returns:
            Dictionary mapping section names to extracted terms
        """
        results = {}
        
        for section_name, section_text in sections.items():
            if not section_text or len(section_text.strip()) < 50:
                continue
            
            print(f"Extracting terms from: {section_name}")
            
            # Split long sections into paragraphs (optional)
            if len(section_text) > 2000:
                # Process first 2000 chars for efficiency
                section_text = section_text[:2000]
            
            result = self.pipeline.process_paragraph_with_context(
                section_text, 
                domain
            )
            
            results[section_name] = result['enriched_terms']
        
        return results
    
    def extract_from_abstract(
        self, 
        abstract: str, 
        domain: str = "general"
    ) -> Dict:
        """
        Extract terms specifically from a paper's abstract.
        
        Args:
            abstract: The abstract text
            domain: The domain/field
        
        Returns:
            Extraction results with terms and definitions
        """
        print("Extracting terms from abstract...")
        return self.extract_from_text(abstract, domain)
    
    def create_glossary(
        self, 
        terms_data: List[Dict], 
        output_format: str = "markdown"
    ) -> str:
        """
        Create a glossary from extracted terms.
        
        Args:
            terms_data: List of term dictionaries from extraction
            output_format: "markdown", "html", or "text"
        
        Returns:
            Formatted glossary string
        """
        if output_format == "markdown":
            return self._create_markdown_glossary(terms_data)
        elif output_format == "html":
            return self._create_html_glossary(terms_data)
        else:
            return self._create_text_glossary(terms_data)
    
    def _create_markdown_glossary(self, terms_data: List[Dict]) -> str:
        """Create a Markdown-formatted glossary."""
        glossary = "# Technical Terms Glossary\n\n"
        
        for i, term_info in enumerate(sorted(terms_data, key=lambda x: x['term'].lower()), 1):
            glossary += f"## {i}. {term_info['term']}\n\n"
            glossary += f"**Definition:** {term_info['definition']}\n\n"
            
            if term_info.get('synonyms'):
                glossary += f"**Synonyms:** {', '.join(term_info['synonyms'])}\n\n"
            
            if term_info.get('related_terms'):
                glossary += f"**Related Terms:** {', '.join(term_info['related_terms'])}\n\n"
            
            if term_info.get('context'):
                glossary += f"**Context:** _{term_info['context']}_\n\n"
            
            glossary += "---\n\n"
        
        return glossary
    
    def _create_html_glossary(self, terms_data: List[Dict]) -> str:
        """Create an HTML-formatted glossary."""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Technical Terms Glossary</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; }
        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        .term { margin: 30px 0; padding: 20px; background: #f8f9fa; border-left: 4px solid #3498db; }
        .term-title { color: #2c3e50; font-size: 1.4em; font-weight: bold; margin-bottom: 10px; }
        .definition { margin: 10px 0; line-height: 1.6; }
        .meta { color: #7f8c8d; font-size: 0.9em; margin: 5px 0; }
        .context { font-style: italic; color: #555; }
    </style>
</head>
<body>
    <h1>Technical Terms Glossary</h1>
"""
        
        for term_info in sorted(terms_data, key=lambda x: x['term'].lower()):
            html += f'    <div class="term">\n'
            html += f'        <div class="term-title">{term_info["term"]}</div>\n'
            html += f'        <div class="definition"><strong>Definition:</strong> {term_info["definition"]}</div>\n'
            
            if term_info.get('synonyms'):
                html += f'        <div class="meta"><strong>Synonyms:</strong> {", ".join(term_info["synonyms"])}</div>\n'
            
            if term_info.get('related_terms'):
                html += f'        <div class="meta"><strong>Related:</strong> {", ".join(term_info["related_terms"])}</div>\n'
            
            if term_info.get('context'):
                html += f'        <div class="context">Context: {term_info["context"]}</div>\n'
            
            html += '    </div>\n'
        
        html += """
</body>
</html>
"""
        return html
    
    def _create_text_glossary(self, terms_data: List[Dict]) -> str:
        """Create a plain text glossary."""
        glossary = "TECHNICAL TERMS GLOSSARY\n"
        glossary += "=" * 80 + "\n\n"
        
        for i, term_info in enumerate(sorted(terms_data, key=lambda x: x['term'].lower()), 1):
            glossary += f"{i}. {term_info['term'].upper()}\n"
            glossary += f"   Definition: {term_info['definition']}\n"
            
            if term_info.get('synonyms'):
                glossary += f"   Synonyms: {', '.join(term_info['synonyms'])}\n"
            
            if term_info.get('related_terms'):
                glossary += f"   Related: {', '.join(term_info['related_terms'])}\n"
            
            if term_info.get('context'):
                glossary += f"   Context: {term_info['context']}\n"
            
            glossary += "\n" + "-" * 80 + "\n\n"
        
        return glossary


def process_research_paper_example():
    """
    Example showing how to process a complete research paper.
    """
    import os
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set")
        return
    
    # Initialize extractor
    extractor = ResearchPaperTermExtractor(model="gpt-4o-mini")
    
    # Example paper sections
    paper_sections = {
        "abstract": """
            This paper presents a novel deep learning approach for image segmentation
            using convolutional neural networks with attention mechanisms. We introduce
            a multi-scale feature extraction method that improves performance on 
            biomedical images. Our model achieves state-of-the-art results on the
            ISBI challenge dataset through transfer learning and data augmentation.
        """,
        "introduction": """
            Image segmentation is a fundamental task in computer vision, with applications
            ranging from autonomous driving to medical diagnosis. Recent advances in
            deep learning, particularly U-Net architectures, have significantly improved
            segmentation accuracy. However, challenges remain in handling multi-scale
            features and maintaining spatial resolution.
        """
    }
    
    print("Processing research paper sections...\n")
    
    # Extract terms from all sections
    results = extractor.extract_from_paper_sections(
        paper_sections, 
        domain="computer science"
    )
    
    # Combine all terms
    all_terms = []
    for section_name, terms in results.items():
        all_terms.extend(terms)
    
    print(f"\nExtracted {len(all_terms)} total technical terms\n")
    
    # Create glossaries in different formats
    print("Creating glossaries...")
    
    # Markdown
    md_glossary = extractor.create_glossary(all_terms, "markdown")
    with open("glossary.md", "w", encoding="utf-8") as f:
        f.write(md_glossary)
    print("✓ Markdown glossary saved to: glossary.md")
    
    # HTML
    html_glossary = extractor.create_glossary(all_terms, "html")
    with open("glossary.html", "w", encoding="utf-8") as f:
        f.write(html_glossary)
    print("✓ HTML glossary saved to: glossary.html")
    
    # JSON
    with open("terms_data.json", "w", encoding="utf-8") as f:
        json.dump({"sections": results, "all_terms": all_terms}, f, indent=2)
    print("✓ JSON data saved to: terms_data.json")
    
    # Display sample
    print("\n" + "=" * 80)
    print("SAMPLE EXTRACTED TERMS")
    print("=" * 80 + "\n")
    
    for term_info in all_terms[:3]:
        print(f"Term: {term_info['term']}")
        print(f"Definition: {term_info['definition'][:150]}...")
        print()


if __name__ == "__main__":
    process_research_paper_example()
