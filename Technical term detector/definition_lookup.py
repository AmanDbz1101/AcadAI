#!/usr/bin/env python3
"""
Multi-layer definition lookup system for technical terms.

Priority order:
1. Paper itself (inline definitions)
2. Wikipedia API
3. Domain ontologies (CS Ontology, INSPIRE-HEP)
4. Local LLM fallback (Ollama)
"""

import re
import time
from typing import Dict, Optional
import requests
import warnings


class DefinitionLookup:
    """
    Multi-layer definition lookup for technical terms.
    
    Implements a cascading lookup strategy that tries multiple sources
    before falling back to LLM generation.
    """
    
    def __init__(self, ollama_model: str = "qwen2.5:3b", ollama_url: str = "http://localhost:11434/api/generate"):
        """
        Initialize the definition lookup system.
        
        Args:
            ollama_model: Model name for Ollama LLM fallback
            ollama_url: URL for Ollama API
        """
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url
        
        # Track statistics
        self.stats = {
            "paper": 0,
            "wikipedia": 0,
            "ontology": 0,
            "llm": 0,
            "not_found": 0
        }
    
    def get_definition(
        self, 
        term: str, 
        context_sentence: str = "", 
        full_text: str = ""
    ) -> Dict[str, Optional[str]]:
        """
        Get definition for a term using cascading lookup strategy.
        
        Args:
            term: Technical term to define
            context_sentence: Sentence containing the term (for LLM context)
            full_text: Full paper text (for inline definition search)
            
        Returns:
            Dict with keys: definition, source, time_taken
        """
        start_time = time.time()
        
        # Layer 1: Check the paper itself first (free, instant, most accurate)
        if full_text:
            definition = self._find_inline_definition(term, full_text)
            if definition:
                self.stats["paper"] += 1
                return {
                    "definition": definition,
                    "source": "paper",
                    "time_taken": time.time() - start_time
                }
        
        # Layer 2: Wikipedia
        definition = self._get_wikipedia_definition(term)
        if definition:
            self.stats["wikipedia"] += 1
            return {
                "definition": definition,
                "source": "wikipedia",
                "time_taken": time.time() - start_time
            }
        
        # Layer 3: Domain ontologies
        # Try CS Ontology first
        definition = self._get_cso_definition(term)
        if definition:
            self.stats["ontology"] += 1
            return {
                "definition": definition,
                "source": "ontology (CSO)",
                "time_taken": time.time() - start_time
            }
        
        # Try INSPIRE-HEP for physics terms
        definition = self._get_inspire_definition(term)
        if definition:
            self.stats["ontology"] += 1
            return {
                "definition": definition,
                "source": "ontology (INSPIRE-HEP)",
                "time_taken": time.time() - start_time
            }
        
        # Layer 4: Local LLM fallback (only novel/niche terms reach here)
        definition = self._get_llm_definition(term, context_sentence)
        if definition and not definition.startswith("Error:"):
            self.stats["llm"] += 1
            return {
                "definition": definition,
                "source": "llm",
                "time_taken": time.time() - start_time
            }
        
        # Not found anywhere
        self.stats["not_found"] += 1
        return {
            "definition": None,
            "source": None,
            "time_taken": time.time() - start_time
        }
    
    def _find_inline_definition(self, term: str, full_text: str) -> Optional[str]:
        """
        Find inline definitions in the paper text.
        
        Patterns:
        - "term, which is ..."
        - "term, defined as ..."
        - "term (explanation)"
        - "term, i.e., ..."
        - "term, also known as ..."
        
        Args:
            term: Term to find definition for
            full_text: Full paper text
            
        Returns:
            Definition string if found, None otherwise
        """
        # Escape special regex characters in term
        escaped_term = re.escape(term)
        
        patterns = [
            rf"{escaped_term},?\s+which\s+is\s+([^.]+)\.",
            rf"{escaped_term},?\s+defined\s+as\s+([^.]+)\.",
            rf"{escaped_term}\s+\(([^)]+)\)",  # parenthetical explanation
            rf"{escaped_term},?\s+i\.e\.?,?\s+([^.]+)\.",
            rf"{escaped_term},?\s+also\s+known\s+as\s+([^.]+)\.",
            rf"{escaped_term},?\s+refers\s+to\s+([^.]+)\.",
            rf"{escaped_term}:\s+([^.]+)\.",  # colon-based definition
        ]
        
        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                definition = match.group(1).strip()
                # Clean up the definition
                definition = re.sub(r'\s+', ' ', definition)
                # Filter out very short or very long matches
                if 10 < len(definition) < 300:
                    return definition
        
        return None
    
    def _get_wikipedia_definition(self, term: str) -> Optional[str]:
        """
        Get definition from Wikipedia API.
        
        Args:
            term: Term to look up
            
        Returns:
            First sentence from Wikipedia summary, or None
        """
        try:
            # Use Wikipedia REST API v1
            # Documentation: https://en.wikipedia.org/api/rest_v1/
            
            # Clean up term for URL
            term_cleaned = term.replace(' ', '_')
            
            # Try to get the summary directly
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{term_cleaned}"
            headers = {
                'User-Agent': 'TechnicalTermDetector/1.0 (Educational Project)'
            }
            
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                extract = data.get('extract', '')
                
                if extract and not extract.startswith('Wikimedia disambiguation page'):
                    # Get first sentence
                    sentences = extract.split('. ')
                    if sentences:
                        first_sentence = sentences[0].strip()
                        # Make sure we have a complete sentence
                        if first_sentence and len(first_sentence) > 20:
                            if not first_sentence.endswith('.'):
                                first_sentence += '.'
                            return first_sentence
            
            # If direct lookup failed, try search
            search_url = "https://en.wikipedia.org/w/api.php"
            search_params = {
                "action": "opensearch",
                "search": term,
                "limit": 1,
                "namespace": 0,
                "format": "json"
            }
            
            response = requests.get(search_url, params=search_params, headers=headers, timeout=5)
            
            if response.status_code == 200:
                search_results = response.json()
                
                if search_results and len(search_results) > 1 and search_results[1]:
                    page_title = search_results[1][0]
                    
                    # Try summary API again with the found title
                    page_title_cleaned = page_title.replace(' ', '_')
                    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{page_title_cleaned}"
                    
                    response = requests.get(summary_url, headers=headers, timeout=5)
                    
                    if response.status_code == 200:
                        data = response.json()
                        extract = data.get('extract', '')
                        
                        if extract and not extract.startswith('Wikimedia disambiguation page'):
                            sentences = extract.split('. ')
                            if sentences:
                                first_sentence = sentences[0].strip()
                                if first_sentence and len(first_sentence) > 20:
                                    if not first_sentence.endswith('.'):
                                        first_sentence += '.'
                                    return first_sentence
            
            return None
            
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.RequestException:
            return None
        except Exception:
            return None
    
    def _get_cso_definition(self, term: str) -> Optional[str]:
        """
        Get definition from Computer Science Ontology (CSO).
        
        Args:
            term: CS term to look up
            
        Returns:
            Definition from CSO, or None
        """
        try:
            # CSO API endpoint
            url = "https://cso.kmi.open.ac.uk/api/v2.0/topics"
            params = {"topic": term.lower()}
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                # CSO returns related topics and metadata
                if isinstance(data, dict) and "abstraction" in data:
                    # Get the abstract or description
                    abstract = data.get("abstraction", "")
                    if abstract:
                        return f"A topic in computer science related to {abstract}."
                
            return None
            
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.RequestException:
            return None
        except Exception:
            return None
    
    def _get_inspire_definition(self, term: str) -> Optional[str]:
        """
        Get definition from INSPIRE-HEP (high energy physics).
        
        Note: This is conservative and only returns results for clearly
        physics-related terms to avoid false positives.
        
        Args:
            term: Physics term to look up
            
        Returns:
            Abstract excerpt from most relevant paper, or None
        """
        # Only try INSPIRE for clearly physics-related terms
        # to avoid pulling irrelevant physics papers for CS terms
        physics_keywords = [
            'quantum', 'particle', 'photon', 'quark', 'lepton',
            'hadron', 'boson', 'fermion', 'neutrino', 'cosmology',
            'relativity', 'gravity', 'spacetime', 'field theory',
            'standard model', 'higgs', 'supersymmetry', 'gauge'
        ]
        
        term_lower = term.lower()
        is_physics = any(kw in term_lower for kw in physics_keywords)
        
        if not is_physics:
            return None
        
        try:
            url = "https://inspirehep.net/api/literature"
            params = {
                "q": f'title:"{term}"',  # Search in titles for more relevant results
                "size": 1,
                "fields": "abstracts,titles",
                "sort": "mostrecent"
            }
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                hits = data.get("hits", {}).get("hits", [])
                
                if hits:
                    metadata = hits[0].get("metadata", {})
                    
                    # Check if the title actually matches our term well
                    titles = metadata.get("titles", [])
                    if titles:
                        title_text = titles[0].get("title", "").lower()
                        if term.lower() not in title_text:
                            return None
                    
                    abstracts = metadata.get("abstracts", [])
                    
                    if abstracts:
                        abstract_text = abstracts[0].get("value", "")
                        # Return first sentence only
                        sentences = abstract_text.split('. ')
                        if sentences and len(sentences[0]) > 50:
                            return sentences[0].strip() + '.'
            
            return None
            
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.RequestException:
            return None
        except Exception:
            return None
    
    def _get_llm_definition(self, term: str, context_sentence: str = "") -> Optional[str]:
        """
        Get definition from local Ollama LLM as last resort.
        
        Args:
            term: Term to define
            context_sentence: Sentence containing the term for context
            
        Returns:
            LLM-generated definition, or None
        """
        try:
            if context_sentence:
                prompt = f"""Define the technical term "{term}" as used in this context:
"{context_sentence}"

Provide a concise, clear definition in 1-2 sentences. Do not include any preamble or extra text."""
            else:
                prompt = f"""Define the technical term "{term}" in the context of computer science and physics.
Provide a concise, clear definition in 1-2 sentences. Do not include any preamble or extra text."""
            
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            definition = result.get("response", "").strip()
            
            return definition if definition else None
            
        except requests.exceptions.ConnectionError:
            return "Error: Cannot connect to Ollama. Make sure Ollama is running (ollama serve)"
        except requests.exceptions.Timeout:
            return "Error: Request timed out"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def print_stats(self):
        """Print statistics about definition sources used."""
        total = sum(self.stats.values())
        
        if total == 0:
            print("\nNo definitions looked up yet.")
            return
        
        print("\n" + "="*60)
        print("DEFINITION SOURCE STATISTICS")
        print("="*60)
        
        for source, count in self.stats.items():
            percentage = (count / total) * 100
            bar_length = int(percentage / 2)  # Scale to 50 chars max
            bar = "█" * bar_length
            
            source_label = source.replace("_", " ").title()
            print(f"{source_label:20} {bar:50} {count:3} ({percentage:5.1f}%)")
        
        print(f"\n{'Total':20} {' '*50} {total:3} (100.0%)")
        print("="*60)
        
        # Calculate efficiency metrics
        free_sources = self.stats["paper"] + self.stats["wikipedia"] + self.stats["ontology"]
        free_percentage = (free_sources / total) * 100 if total > 0 else 0
        
        print(f"\nFree sources (paper/Wikipedia/ontology): {free_sources}/{total} ({free_percentage:.1f}%)")
        print(f"LLM usage: {self.stats['llm']}/{total} ({(self.stats['llm']/total*100) if total > 0 else 0:.1f}%)")
