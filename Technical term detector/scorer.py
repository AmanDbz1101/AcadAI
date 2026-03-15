"""
Scoring and filtering module for technical term detection.
Calculates confidence scores and filters out non-technical terms.
"""

from typing import List, Dict, Set
from collections import Counter
import wordfreq


class TermScorer:
    """Scores and filters technical term candidates."""
    
    def __init__(self):
        # Generic academic phrases to filter out
        self.generic_phrases = {
            'proposed method', 'previous work', 'et al', 'in this paper',
            'we show', 'results show', 'can be', 'is used', 'such as',
            'based on', 'in order', 'this work', 'our method', 'our approach',
            'in this work', 'we propose', 'we present', 'we use',
            'can be seen', 'it is', 'there are', 'there is', 'as well',
            'note that', 'we note', 'in addition', 'as shown', 'we can'
        }
        
        # Common English stopwords
        self.stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
            'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are',
            'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do',
            'does', 'did', 'will', 'would', 'could', 'should', 'may',
            'might', 'must', 'can', 'this', 'that', 'these', 'those'
        }
    
    def score_terms(
        self,
        candidates: List[Dict[str, any]],
        text: str,
        scispacy_terms: Set[str]
    ) -> List[Dict[str, any]]:
        """
        Score all term candidates and filter out low-quality terms.
        
        Args:
            candidates: List of candidate terms with 'term' and 'type' keys
            text: Original input text for frequency calculation
            scispacy_terms: Set of terms detected by SciSpaCy (these get special treatment)
            
        Returns:
            Filtered and scored list of terms
        """
        # Calculate term frequencies in the text
        text_lower = text.lower()
        term_counts = Counter()
        
        for candidate in candidates:
            term_lower = candidate['term'].lower()
            term_counts[term_lower] = text_lower.count(term_lower)
        
        # Find max frequency for normalization
        max_freq = max(term_counts.values()) if term_counts else 1
        
        # Score each candidate
        scored_terms = []
        for candidate in candidates:
            term = candidate['term']
            term_lower = term.lower()
            
            # Skip if should be filtered
            if self._should_filter(term, term_lower, scispacy_terms):
                continue
            
            # Calculate score components
            term_freq_normalized = term_counts[term_lower] / max_freq
            rarity_score = self._calculate_rarity(term_lower)
            length_bonus = min(len(term.split()), 3) / 3
            
            # Final score: weighted combination
            final_score = (
                term_freq_normalized * 0.3 +
                rarity_score * 0.5 +
                length_bonus * 0.2
            )
            
            # Apply minimum score threshold
            if final_score >= 0.3:
                scored_terms.append({
                    'term': term,
                    'type': candidate['type'],
                    'score': round(final_score, 2),
                    **({k: v for k, v in candidate.items() 
                        if k not in ['term', 'type', 'span']})
                })
        
        # Sort by score descending
        scored_terms.sort(key=lambda x: x['score'], reverse=True)
        
        return scored_terms
    
    def _calculate_rarity(self, term: str) -> float:
        """
        Calculate rarity score using wordfreq library.
        
        Args:
            term: Term to score
            
        Returns:
            Rarity score between 0 and 1 (higher = more rare/technical)
        """
        try:
            freq = wordfreq.word_frequency(term, 'en')
            return 1 - min(freq * 10000, 1.0)  # Scale and cap at 1.0
        except Exception:
            # If wordfreq fails, assume it's rare/technical
            return 0.8
    
    def _should_filter(
        self,
        term: str,
        term_lower: str,
        scispacy_terms: Set[str]
    ) -> bool:
        """
        Determine if a term should be filtered out.
        
        Args:
            term: Original term
            term_lower: Lowercase version of term
            scispacy_terms: Terms detected by SciSpaCy
            
        Returns:
            True if term should be filtered out
        """
        # Keep if too short (less than 2 chars)
        if len(term) < 2:
            return True
        
        # Filter pure stopwords
        if term_lower in self.stopwords:
            return True
        
        # Filter generic academic phrases
        if term_lower in self.generic_phrases:
            return True
        
        # For single words: filter common English words unless SciSpaCy caught it
        words = term.split()
        if len(words) == 1 and term_lower not in scispacy_terms:
            try:
                freq = wordfreq.word_frequency(term_lower, 'en')
                if freq > 0.0001:  # Common English word threshold
                    return True
            except Exception:
                pass
        
        return False
