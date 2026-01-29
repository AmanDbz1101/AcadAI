"""
Alternative: SciSpacy-based Technical Term Extraction
Uses biomedical/scientific NLP models for domain-specific term extraction.

NOTE: This implementation has known compatibility issues with newer spaCy versions.
For production use, please use term_extractor.py (KeyBERT-based) instead.
"""

from typing import List
from collections import OrderedDict
import spacy
import warnings


# Global model cache
_scispacy_model = None
_use_fallback = False


def _get_scispacy_model():
    """Lazy load SciSpacy model with fallback to regular spaCy."""
    global _scispacy_model, _use_fallback
    
    if _use_fallback:
        # Use regular spaCy model as fallback
        try:
            _scispacy_model = spacy.load('en_core_web_sm')
        except OSError:
            import os
            os.system('python -m spacy download en_core_web_sm')
            _scispacy_model = spacy.load('en_core_web_sm')
        return _scispacy_model
    
    if _scispacy_model is None:
        try:
            _scispacy_model = spacy.load('en_core_sci_sm')
        except (OSError, ModuleNotFoundError, ImportError) as e:
            warnings.warn(
                f"SciSpacy model loading failed: {e}\n"
                "Falling back to en_core_web_sm. "
                "For better scientific term extraction, resolve SciSpacy compatibility issues."
            )
            _use_fallback = True
            # Load fallback model
            try:
                _scispacy_model = spacy.load('en_core_web_sm')
            except OSError:
                import os
                print("Downloading en_core_web_sm model...")
                os.system('python -m spacy download en_core_web_sm')
                _scispacy_model = spacy.load('en_core_web_sm')
    return _scispacy_model


def _is_technical_term(token) -> bool:
    """Check if a token is likely a technical term."""
    # Technical terms are usually nouns or proper nouns
    if token.pos_ not in ['NOUN', 'PROPN']:
        return False
    
    # Skip pronouns and very short words
    if token.is_stop or len(token.text) < 3:
        return False
    
    # Prefer capitalized words (often technical/proper nouns)
    # or words with specific patterns
    if token.text[0].isupper() or '_' in token.text or '-' in token.text:
        return True
    
    # Check if word has technical suffix patterns
    technical_suffixes = ('tion', 'sion', 'ment', 'ness', 'ity', 'ism', 'sis')
    if any(token.text.lower().endswith(suffix) for suffix in technical_suffixes):
        return True
    
    return not token.is_stop


def extract_technical_terms(paragraph: str, top_n: int = 20) -> List[str]:
    """
    Extract technical terms using SciSpacy scientific language model.
    
    Args:
        paragraph: Input text paragraph
        top_n: Maximum number of terms to return
    
    Returns:
        List of technical terms, deduplicated
    """
    if not paragraph or len(paragraph.strip()) < 10:
        return []
    
    nlp = _get_scispacy_model()
    doc = nlp(paragraph)
    
    terms = []
    seen_lower = set()
    
    # Extract noun chunks (multi-word technical phrases)
    for chunk in doc.noun_chunks:
        # Filter by root token
        if _is_technical_term(chunk.root):
            term = chunk.text.strip()
            term_lower = term.lower()
            
            # Skip very long chunks
            if len(term.split()) <= 4 and term_lower not in seen_lower:
                terms.append(term)
                seen_lower.add(term_lower)
    
    # Extract individual technical nouns
    for token in doc:
        if _is_technical_term(token):
            term = token.text.strip()
            term_lower = term.lower()
            
            if term_lower not in seen_lower:
                terms.append(term)
                seen_lower.add(term_lower)
    
    # Deduplicate while preserving order
    final_terms = list(OrderedDict.fromkeys(terms))
    
    return final_terms[:top_n]


if __name__ == "__main__":
    # Sample scientific paragraph
    sample_paragraph = """
    The mitochondrial electron transport chain comprises four protein complexes 
    that facilitate oxidative phosphorylation. Complex I (NADH dehydrogenase) 
    accepts electrons from NADH, while Complex II (succinate dehydrogenase) 
    receives electrons from FADH2. These electrons traverse through Complex III 
    (cytochrome bc1 complex) and Complex IV (cytochrome c oxidase), ultimately 
    reducing molecular oxygen to water. The proton gradient generated across 
    the inner mitochondrial membrane drives ATP synthase to produce adenosine 
    triphosphate through chemiosmotic coupling.
    """
    
    print("Extracting technical terms with SciSpacy...\n")
    terms = extract_technical_terms(sample_paragraph, top_n=15)
    
    print(f"Found {len(terms)} technical terms:")
    for i, term in enumerate(terms, 1):
        print(f"{i}. {term}")
