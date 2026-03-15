"""
Core technical term detection pipeline.
Orchestrates acronym extraction, NER, POS matching, and scoring.
"""

import warnings
from typing import List, Dict, Set, Tuple
import spacy
from spacy.matcher import Matcher

from acronym_extractor import AcronymExtractor
from scorer import TermScorer


class TechnicalTermDetector:
    """Main pipeline for detecting technical terms in scientific text."""
    
    def __init__(self):
        """Initialize the detector with NLP models and extractors."""
        self.acronym_extractor = AcronymExtractor()
        self.scorer = TermScorer()
        self.nlp = self._load_spacy_model()
        self.matcher = self._setup_matcher()
    
    def _load_spacy_model(self):
        """Load SciSpaCy model with fallback to standard spaCy."""
        try:
            nlp = spacy.load("en_core_sci_lg")
        except OSError:
            warnings.warn(
                "SciSpaCy model 'en_core_sci_lg' not found. "
                "Falling back to 'en_core_web_sm'. "
                "For better results, install SciSpaCy: "
                "pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/"
                "releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz"
            )
            try:
                nlp = spacy.load("en_core_web_sm")
            except OSError:
                raise OSError(
                    "No spaCy model found. Please install at least en_core_web_sm: "
                    "python -m spacy download en_core_web_sm"
                )
        return nlp
    
    def _setup_matcher(self) -> Matcher:
        """Set up spaCy Matcher with POS patterns for technical terms."""
        matcher = Matcher(self.nlp.vocab)
        
        # Pattern 1: ADJ + NOUN
        matcher.add("ADJ_NOUN", [[{"POS": "ADJ"}, {"POS": "NOUN"}]])
        
        # Pattern 2: NOUN + NOUN
        matcher.add("NOUN_NOUN", [[{"POS": "NOUN"}, {"POS": "NOUN"}]])
        
        # Pattern 3: NOUN + NOUN + NOUN
        matcher.add("NOUN_NOUN_NOUN", [
            [{"POS": "NOUN"}, {"POS": "NOUN"}, {"POS": "NOUN"}]
        ])
        
        # Pattern 4: NOUN + of + NOUN
        matcher.add("NOUN_OF_NOUN", [
            [{"POS": "NOUN"}, {"LOWER": "of"}, {"POS": "NOUN"}]
        ])
        
        # Pattern 5: ADJ + ADJ + NOUN
        matcher.add("ADJ_ADJ_NOUN", [
            [{"POS": "ADJ"}, {"POS": "ADJ"}, {"POS": "NOUN"}]
        ])
        
        return matcher
    
    def detect(self, text: str) -> List[Dict[str, any]]:
        """
        Detect technical terms in the given text.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Ranked list of technical terms with scores
        """
        if not text or not text.strip():
            return []
        
        # Process text with spaCy
        doc = self.nlp(text)
        
        # Step 1: Extract acronyms
        acronyms = self.acronym_extractor.extract_acronyms(text)
        
        # Step 2: SciSpaCy NER
        ner_terms = self._extract_ner_terms(doc)
        
        # Step 3: Noun chunks
        noun_chunks = self._extract_noun_chunks(doc)
        
        # Step 4: POS pattern matching
        pattern_matches = self._extract_pattern_matches(doc)
        
        # Step 5: Merge and deduplicate
        all_candidates = self._merge_candidates(
            acronyms, ner_terms, noun_chunks, pattern_matches, text
        )
        
        # Step 6: Score and filter
        scispacy_terms = {t['term'].lower() for t in ner_terms}
        scored_terms = self.scorer.score_terms(all_candidates, text, scispacy_terms)
        
        return scored_terms
    
    def _extract_ner_terms(self, doc) -> List[Dict[str, any]]:
        """Extract named entities from spaCy doc."""
        terms = []
        for ent in doc.ents:
            terms.append({
                'term': ent.text,
                'type': 'multi-word' if len(ent.text.split()) > 1 else 'single-word',
                'span': (ent.start_char, ent.end_char)
            })
        return terms
    
    def _extract_noun_chunks(self, doc) -> List[Dict[str, any]]:
        """Extract noun phrases from spaCy doc."""
        terms = []
        for chunk in doc.noun_chunks:
            # Clean up the chunk (remove leading determiners)
            text = chunk.text.strip()
            if text.split()[0].lower() in ['the', 'a', 'an']:
                text = ' '.join(text.split()[1:])
            
            if text:
                terms.append({
                    'term': text,
                    'type': 'multi-word' if len(text.split()) > 1 else 'single-word',
                    'span': (chunk.start_char, chunk.end_char)
                })
        return terms
    
    def _extract_pattern_matches(self, doc) -> List[Dict[str, any]]:
        """Extract terms matching POS patterns."""
        matches = self.matcher(doc)
        terms = []
        
        for match_id, start, end in matches:
            span = doc[start:end]
            terms.append({
                'term': span.text,
                'type': 'multi-word' if len(span.text.split()) > 1 else 'single-word',
                'span': (span.start_char, span.end_char)
            })
        
        return terms
    
    def _merge_candidates(
        self,
        acronyms: List[Dict],
        ner_terms: List[Dict],
        noun_chunks: List[Dict],
        pattern_matches: List[Dict],
        text: str
    ) -> List[Dict[str, any]]:
        """Merge all candidates and remove duplicates/overlaps."""
        # Combine all candidates
        all_candidates = acronyms + ner_terms + noun_chunks + pattern_matches
        
        # Remove exact duplicates and handle overlapping spans
        unique_candidates = {}
        
        for candidate in all_candidates:
            term_lower = candidate['term'].lower()
            span = candidate.get('span', (0, 0))
            
            # If we haven't seen this term, add it
            if term_lower not in unique_candidates:
                unique_candidates[term_lower] = candidate
            else:
                # If we have seen it, keep the one with more information
                existing = unique_candidates[term_lower]
                if 'expansion' in candidate and 'expansion' not in existing:
                    unique_candidates[term_lower] = candidate
        
        # Resolve overlapping spans by keeping longest match
        final_candidates = self._resolve_overlaps(list(unique_candidates.values()))
        
        return final_candidates
    
    def _resolve_overlaps(self, candidates: List[Dict]) -> List[Dict]:
        """Keep longest match when spans overlap."""
        # Sort by start position
        sorted_candidates = sorted(
            candidates,
            key=lambda x: (x.get('span', (0, 0))[0], -len(x['term']))
        )
        
        kept = []
        for candidate in sorted_candidates:
            span = candidate.get('span', (0, 0))
            
            # Check if this overlaps with any kept candidate
            overlaps = False
            for kept_candidate in kept:
                kept_span = kept_candidate.get('span', (0, 0))
                if self._spans_overlap(span, kept_span):
                    overlaps = True
                    break
            
            if not overlaps:
                kept.append(candidate)
        
        return kept
    
    def _spans_overlap(self, span1: Tuple[int, int], span2: Tuple[int, int]) -> bool:
        """Check if two character spans overlap."""
        return not (span1[1] <= span2[0] or span2[1] <= span1[0])
