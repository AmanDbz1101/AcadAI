"""
LLM-Based Technical Term Extraction and Definition Module

This module uses Large Language Models (LLMs) via LangChain and Groq API to:
1. Extract technical terms from paragraphs
2. Find meanings/definitions of extracted technical terms

Powered by Groq's fast inference API with openai/gpt-oss-120b model.
"""

import os
import json
from typing import List, Dict, Tuple
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv

load_dotenv()

class LLMTermExtractor:
    """
    Extract technical terms from text using LLM-based analysis.
    """
    
    def __init__(self, api_key: str = None, model: str = "openai/gpt-oss-120b"):
        """
        Initialize the LLM Term Extractor.
        
        Args:
            api_key: Groq API key (if None, will use GROQ_API_KEY environment variable)
            model: Groq model to use (default: openai/gpt-oss-120b)
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Groq API key must be provided or set in GROQ_API_KEY environment variable")
        
        self.model = model
        self.llm = ChatGroq(
            api_key=self.api_key,
            model=self.model,
            temperature=0.3
        )
    
    def extract_terms(self, paragraph: str, domain: str = "general") -> List[str]:
        """
        Extract technical terms from a paragraph using LLM.
        
        Args:
            paragraph: The input text paragraph
            domain: The domain/field of study (e.g., "machine learning", "biology", "physics")
        
        Returns:
            List of extracted technical terms
        """
        prompt = f"""You are an expert at identifying technical terms in academic and research text.

Domain: {domain}

Analyze the following paragraph and extract ALL technical terms, concepts, and specialized vocabulary. Include:
- Domain-specific terminology
- Scientific concepts
- Methodologies and techniques
- Specialized abbreviations and acronyms
- Technical processes
- Mathematical or scientific notations (spelled out)

Paragraph:
{paragraph}

Return ONLY a JSON array of technical terms, without any additional explanation.
Format: ["term1", "term2", "term3", ...]

Rules:
- Include only substantive technical terms (not common words)
- Preserve the exact form as it appears in the text
- Include multi-word terms as single entries
- Do not include generic words like "method", "approach", "study" unless they are part of a specific technical term
"""

        try:
            messages = [
                SystemMessage(content="You are a technical term extraction expert. Always respond with valid JSON arrays."),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            content = response.content
            
            # Parse the JSON response
            result = json.loads(content)
            
            # Handle different possible response formats
            if isinstance(result, list):
                terms = result
            elif isinstance(result, dict):
                # Try common keys
                terms = result.get('terms', result.get('technical_terms', result.get('keywords', [])))
            else:
                terms = []
            
            return terms
            
        except Exception as e:
            print(f"Error extracting terms: {e}")
            return []
    
    def extract_terms_with_context(self, paragraph: str, domain: str = "general") -> List[Dict[str, str]]:
        """
        Extract technical terms with their contextual usage from the paragraph.
        
        Args:
            paragraph: The input text paragraph
            domain: The domain/field of study
        
        Returns:
            List of dictionaries containing term and its context
        """
        prompt = f"""You are an expert at identifying technical terms in academic and research text.

Domain: {domain}

Analyze the following paragraph and extract ALL technical terms along with a brief context of how they are used in the text.

Paragraph:
{paragraph}

Return a JSON object with a "terms" key containing an array of objects. Each object should have:
- "term": the technical term
- "context": a brief phrase showing how it's used in the paragraph (5-10 words)

Example format:
{{
  "terms": [
    {{"term": "neural network", "context": "used for image classification"}},
    {{"term": "backpropagation", "context": "training algorithm for the network"}}
  ]
}}

Rules:
- Include only substantive technical terms
- Context should be concise and specific
- Preserve the exact form of terms as they appear
"""

        try:
            messages = [
                SystemMessage(content="You are a technical term extraction expert. Always respond with valid JSON."),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            content = response.content
            result = json.loads(content)
            
            terms_with_context = result.get('terms', [])
            return terms_with_context
            
        except Exception as e:
            print(f"Error extracting terms with context: {e}")
            return []


class LLMTermDefinitionFinder:
    """
    Find meanings and definitions of technical terms using LLM.
    """
    
    def __init__(self, api_key: str = None, model: str = "openai/gpt-oss-120b"):
        """
        Initialize the LLM Term Definition Finder.
        
        Args:
            api_key: Groq API key (if None, will use GROQ_API_KEY environment variable)
            model: Groq model to use
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Groq API key must be provided or set in GROQ_API_KEY environment variable")
        
        self.model = model
        self.llm = ChatGroq(
            api_key=self.api_key,
            model=self.model,
            temperature=0.3
        )
    
    def find_definition(self, term: str, domain: str = "general", context: str = None) -> Dict[str, str]:
        """
        Find the definition of a single technical term.
        
        Args:
            term: The technical term to define
            domain: The domain/field of study
            context: Optional context from the original paragraph
        
        Returns:
            Dictionary containing the term and its definition
        """
        context_info = f"\n\nContext from source text: {context}" if context else ""
        
        prompt = f"""You are an expert in providing clear, accurate definitions of technical terms.

Domain: {domain}
Term: {term}{context_info}

Provide a clear, concise definition of this technical term that would be appropriate for an academic or research context.

Return a JSON object with the following structure:
{{
  "term": "{term}",
  "definition": "A clear, concise definition (2-4 sentences)",
  "domain": "The specific field/domain where this term is primarily used",
  "synonyms": ["list", "of", "synonyms"],
  "related_terms": ["list", "of", "related", "terms"]
}}

Rules:
- Definition should be accurate and academic in nature
- Include 2-5 synonyms if applicable (empty array if none)
- Include 2-5 related terms (empty array if none)
- If the term is ambiguous, provide the definition most relevant to the specified domain
"""

        try:
            messages = [
                SystemMessage(content="You are an expert at providing technical definitions. Always respond with valid JSON."),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            content = response.content
            definition_data = json.loads(content)
            
            return definition_data
            
        except Exception as e:
            print(f"Error finding definition for '{term}': {e}")
            return {
                "term": term,
                "definition": "Definition not available",
                "domain": domain,
                "synonyms": [],
                "related_terms": []
            }
    
    def find_definitions_batch(self, terms: List[str], domain: str = "general") -> List[Dict[str, str]]:
        """
        Find definitions for multiple technical terms in a single API call.
        
        Args:
            terms: List of technical terms to define
            domain: The domain/field of study
        
        Returns:
            List of dictionaries containing terms and their definitions
        """
        if not terms:
            return []
        
        terms_list = "\n".join([f"- {term}" for term in terms])
        
        prompt = f"""You are an expert in providing clear, accurate definitions of technical terms.

Domain: {domain}

Provide definitions for the following technical terms:
{terms_list}

Return a JSON object with a "definitions" key containing an array of objects. Each object should have:
{{
  "term": "the technical term",
  "definition": "A clear, concise definition (2-4 sentences)",
  "domain": "The specific field/domain",
  "synonyms": ["list of synonyms"],
  "related_terms": ["list of related terms"]
}}

Example format:
{{
  "definitions": [
    {{
      "term": "neural network",
      "definition": "A computational model inspired by biological neural networks...",
      "domain": "Machine Learning",
      "synonyms": ["artificial neural network", "ANN"],
      "related_terms": ["deep learning", "perceptron", "backpropagation"]
    }}
  ]
}}

Rules:
- Provide accurate, academic definitions
- Include 2-5 synonyms if applicable
- Include 2-5 related terms
- Be concise but comprehensive
"""

        try:
            messages = [
                SystemMessage(content="You are an expert at providing technical definitions. Always respond with valid JSON."),
                HumanMessage(content=prompt)
            ]
            
            response = self.llm.invoke(messages)
            content = response.content
            result = json.loads(content)
            
            definitions = result.get('definitions', [])
            return definitions
            
        except Exception as e:
            print(f"Error finding batch definitions: {e}")
            # Return basic structure for all terms
            return [
                {
                    "term": term,
                    "definition": "Definition not available",
                    "domain": domain,
                    "synonyms": [],
                    "related_terms": []
                }
                for term in terms
            ]


class LLMTermExtractorPipeline:
    """
    Complete pipeline combining term extraction and definition finding.
    """
    
    def __init__(self, api_key: str = None, model: str = "openai/gpt-oss-120b"):
        """
        Initialize the complete pipeline.
        
        Args:
            api_key: Groq API key
            model: Groq model to use
        """
        self.extractor = LLMTermExtractor(api_key=api_key, model=model)
        self.definition_finder = LLMTermDefinitionFinder(api_key=api_key, model=model)
    
    def process_paragraph(self, paragraph: str, domain: str = "general") -> Dict[str, any]:
        """
        Complete processing: extract terms and find their definitions.
        
        Args:
            paragraph: Input paragraph text
            domain: The domain/field of study
        
        Returns:
            Dictionary containing terms and their complete information
        """
        print(f"Extracting technical terms from paragraph...")
        terms = self.extractor.extract_terms(paragraph, domain)
        
        print(f"Found {len(terms)} technical terms")
        print(f"Finding definitions...")
        
        definitions = self.definition_finder.find_definitions_batch(terms, domain)
        
        result = {
            "paragraph": paragraph,
            "domain": domain,
            "total_terms": len(terms),
            "terms": terms,
            "definitions": definitions
        }
        
        return result
    
    def process_paragraph_with_context(self, paragraph: str, domain: str = "general") -> Dict[str, any]:
        """
        Enhanced processing: extract terms with context and find their definitions.
        
        Args:
            paragraph: Input paragraph text
            domain: The domain/field of study
        
        Returns:
            Dictionary containing terms with context and their definitions
        """
        print(f"Extracting technical terms with context...")
        terms_with_context = self.extractor.extract_terms_with_context(paragraph, domain)
        
        print(f"Found {len(terms_with_context)} technical terms")
        print(f"Finding definitions...")
        
        # Extract just the terms for batch definition lookup
        terms = [item['term'] for item in terms_with_context]
        definitions = self.definition_finder.find_definitions_batch(terms, domain)
        
        # Merge context and definitions
        enriched_terms = []
        for term_ctx in terms_with_context:
            term = term_ctx['term']
            # Find matching definition
            definition = next((d for d in definitions if d['term'].lower() == term.lower()), None)
            
            enriched_terms.append({
                "term": term,
                "context": term_ctx.get('context', ''),
                "definition": definition['definition'] if definition else "Definition not available",
                "domain_specific": definition['domain'] if definition else domain,
                "synonyms": definition['synonyms'] if definition else [],
                "related_terms": definition['related_terms'] if definition else []
            })
        
        result = {
            "paragraph": paragraph,
            "domain": domain,
            "total_terms": len(enriched_terms),
            "enriched_terms": enriched_terms
        }
        
        return result


# Example usage and testing functions
def main():
    """
    Example usage of the LLM-based term extractor and definition finder.
    """
    # Sample paragraph from a machine learning paper
    sample_paragraph = """
    Deep neural networks have revolutionized computer vision tasks through 
    convolutional architectures. The backpropagation algorithm enables efficient 
    training of multi-layer networks by computing gradients via the chain rule. 
    Batch normalization has been shown to accelerate convergence and improve 
    generalization by normalizing layer inputs. Recent advances in attention 
    mechanisms, particularly the transformer architecture, have achieved 
    state-of-the-art results on image classification benchmarks.
    """
    
    print("=" * 80)
    print("LLM-Based Technical Term Extraction and Definition Demo")
    print("=" * 80)
    
    # Check for API key
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("\nError: GROQ_API_KEY environment variable not set.")
        print("Please set it with: export GROQ_API_KEY='your-api-key-here'")
        return
    
    try:
        # Initialize pipeline
        pipeline = LLMTermExtractorPipeline(model="openai/gpt-oss-120b")
        
        # Process paragraph with context
        print("\nProcessing paragraph with context-aware extraction...\n")
        result = pipeline.process_paragraph_with_context(
            sample_paragraph, 
            domain="machine learning"
        )
        
        # Display results
        print(f"\nOriginal Paragraph:")
        print(f"{result['paragraph']}\n")
        print(f"Domain: {result['domain']}")
        print(f"Total Technical Terms Found: {result['total_terms']}")
        print("\n" + "=" * 80)
        print("EXTRACTED TERMS WITH DEFINITIONS")
        print("=" * 80 + "\n")
        
        for i, term_info in enumerate(result['enriched_terms'], 1):
            print(f"{i}. Term: {term_info['term']}")
            print(f"   Context: {term_info['context']}")
            print(f"   Definition: {term_info['definition']}")
            if term_info['synonyms']:
                print(f"   Synonyms: {', '.join(term_info['synonyms'])}")
            if term_info['related_terms']:
                print(f"   Related: {', '.join(term_info['related_terms'])}")
            print()
        
        # Save results to file
        output_file = "term_extraction_results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved to: {output_file}")
        
    except Exception as e:
        print(f"\nError: {e}")
        print("\nPlease ensure:")
        print("1. GROQ_API_KEY environment variable is set")
        print("2. You have an active Groq API account with available credits")
        print("3. You have internet connectivity")


if __name__ == "__main__":
    main()
