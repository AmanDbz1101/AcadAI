"""
Acronym extraction module for technical term detection.
Handles both expanded acronyms (e.g., "Machine Learning (ML)") and standalone acronyms.
"""

import re
from typing import List, Dict, Tuple


class AcronymExtractor:
    """Extracts acronyms from scientific text using regex patterns."""
    
    def __init__(self):
        # Pattern for expanded acronyms: "Full Name (ABC)"
        self.expanded_pattern = re.compile(
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(([A-Z]{2,6})\)'
        )
        # Pattern for standalone uppercase acronyms (2-6 chars)
        self.standalone_pattern = re.compile(r'\b[A-Z]{2,6}\b')
    
    def extract_acronyms(self, text: str) -> List[Dict[str, any]]:
        """
        Extract all acronyms from the given text.
        
        Args:
            text: Input text to process
            
        Returns:
            List of dicts with keys: 'term', 'type', 'expansion' (optional), 'span'
        """
        acronyms = []
        seen_acronyms = set()
        
        # First pass: Find expanded acronyms (e.g., "Neural Network (NN)")
        for match in self.expanded_pattern.finditer(text):
            expansion = match.group(1)
            acronym = match.group(2)
            
            # Store the linked pair
            acronyms.append({
                'term': acronym,
                'type': 'acronym',
                'expansion': expansion,
                'span': (match.start(2), match.end(2))
            })
            seen_acronyms.add(acronym)
        
        # Second pass: Find standalone acronyms not already captured
        for match in self.standalone_pattern.finditer(text):
            acronym = match.group(0)
            
            # Skip common non-acronyms and already captured ones
            if self._is_likely_acronym(acronym) and acronym not in seen_acronyms:
                acronyms.append({
                    'term': acronym,
                    'type': 'acronym',
                    'span': (match.start(), match.end())
                })
                seen_acronyms.add(acronym)
        
        return acronyms
    
    def _is_likely_acronym(self, text: str) -> bool:
        """
        Filter out uppercase words that are unlikely to be acronyms.
        
        Args:
            text: Candidate acronym string
            
        Returns:
            True if text is likely an acronym
        """
        # Common English words in all caps that aren't acronyms
        common_words = {
            'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL',
            'CAN', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET',
            'HAS', 'HIM', 'HIS', 'HOW', 'ITS', 'MAY', 'NEW', 'NOW',
            'OLD', 'SEE', 'TWO', 'WAY', 'WHO', 'BOY', 'DID', 'GOT',
            'LET', 'PUT', 'SAY', 'SHE', 'TOO', 'USE', 'YES'
        }
        
        return text not in common_words
