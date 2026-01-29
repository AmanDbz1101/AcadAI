"""
Technical Term Extraction Module
Extracts domain-specific terms from academic/research text using KeyBERT.
"""

from typing import List, Set
from keybert import KeyBERT
import spacy
from collections import OrderedDict


# Initialize models globally for reuse
_keybert_model = None
_nlp_model = None


def _get_keybert_model():
    """Lazy load KeyBERT model with lightweight sentence transformer."""
    global _keybert_model
    if _keybert_model is None:
        _keybert_model = KeyBERT(model='all-MiniLM-L6-v2')
    return _keybert_model


def _get_nlp_model():
    """Lazy load spaCy model for POS tagging and noun phrase extraction."""
    global _nlp_model
    if _nlp_model is None:
        try:
            _nlp_model = spacy.load('en_core_web_sm')
        except OSError:
            # Fallback: download if not available
            import os
            os.system('python -m spacy download en_core_web_sm')
            _nlp_model = spacy.load('en_core_web_sm')
    return _nlp_model


def _filter_common_words(terms: List[str]) -> List[str]:
    """Remove common English words and non-technical terms."""
    # Common academic words that are not technical terms
    stopwords = {
        'paper', 'study', 'research', 'method', 'approach', 'result', 'conclusion',
        'analysis', 'data', 'model', 'system', 'work', 'problem', 'solution',
        'time', 'way', 'case', 'example', 'thing', 'use', 'number', 'part',
        'information', 'process', 'table', 'figure', 'section', 'chapter',
        'author', 'article', 'journal', 'page', 'year', 'today', 'yesterday'
    }
    
    filtered = []
    for term in terms:
        # Skip if term is too short or contains only common words
        words = term.lower().split()
        if len(term) < 3 or all(w in stopwords for w in words):
            continue
        # Skip if term is purely numeric or has special characters only
        if not any(c.isalpha() for c in term):
            continue
        filtered.append(term)
    
    return filtered


def _extract_noun_phrases(text: str, nlp) -> List[str]:
    """Extract noun phrases using spaCy."""
    doc = nlp(text)
    noun_phrases = []
    
    # Extract noun chunks
    for chunk in doc.noun_chunks:
        # Filter out single pronouns and determiners
        if chunk.root.pos_ in ['NOUN', 'PROPN']:
            noun_phrases.append(chunk.text.strip())
    
    # Also extract individual nouns that might be technical terms
    for token in doc:
        if token.pos_ in ['NOUN', 'PROPN'] and not token.is_stop:
            noun_phrases.append(token.text)
    
    return noun_phrases


def extract_technical_terms(paragraph: str, top_n: int = 20, diversity: float = 0.5) -> List[str]:
    """
    Extract technical or domain-specific terms from academic text.
    
    Args:
        paragraph: Input text paragraph
        top_n: Maximum number of terms to extract
        diversity: Diversity of results (0-1), higher = more diverse terms
    
    Returns:
        List of technical terms (nouns/noun phrases), deduplicated
    """
    if not paragraph or len(paragraph.strip()) < 10:
        return []
    
    # Load models
    kw_model = _get_keybert_model()
    nlp = _get_nlp_model()
    
    # Step 1: Extract noun phrases using spaCy
    noun_phrases = _extract_noun_phrases(paragraph, nlp)
    
    # Step 2: Use KeyBERT to identify most relevant/technical terms
    # Using MMR (Maximal Marginal Relevance) for diversity
    try:
        keywords = kw_model.extract_keywords(
            paragraph,
            keyphrase_ngram_range=(1, 3),  # Extract 1-3 word phrases
            stop_words='english',
            top_n=top_n * 2,  # Extract more, then filter
            use_mmr=True,
            diversity=diversity
        )
        # KeyBERT returns tuples of (term, score)
        keybert_terms = [term for term, score in keywords if score > 0.3]
    except Exception:
        # Fallback if KeyBERT fails
        keybert_terms = []
    
    # Step 3: Combine and prioritize KeyBERT results with noun phrases
    combined_terms = []
    seen_lower = set()
    
    # Prioritize KeyBERT terms (more likely to be technical)
    for term in keybert_terms:
        term_clean = term.strip()
        term_lower = term_clean.lower()
        if term_lower not in seen_lower:
            combined_terms.append(term_clean)
            seen_lower.add(term_lower)
    
    # Add noun phrases that weren't captured by KeyBERT
    for phrase in noun_phrases:
        phrase_clean = phrase.strip()
        phrase_lower = phrase_clean.lower()
        if phrase_lower not in seen_lower and len(phrase_clean) > 2:
            combined_terms.append(phrase_clean)
            seen_lower.add(phrase_lower)
    
    # Step 4: Filter common words and limit results
    filtered_terms = _filter_common_words(combined_terms)
    
    # Step 5: Remove duplicates while preserving order
    final_terms = list(OrderedDict.fromkeys(filtered_terms))
    
    return final_terms[:top_n]


# Example usage
if __name__ == "__main__":
    # Sample academic paragraph
    sample_paragraph = """
    Deep learning architectures, particularly convolutional neural networks (CNNs) 
    and transformer models, have revolutionized natural language processing tasks. 
    The attention mechanism enables models to focus on relevant input tokens, 
    while gradient descent optimization with backpropagation trains the neural network 
    parameters. Recent advances in transfer learning, such as BERT and GPT, leverage 
    large-scale pretraining on unlabeled corpora followed by fine-tuning on 
    downstream tasks. The self-attention layers in transformers compute contextualized 
    embeddings that capture semantic relationships between words.
    """
    
    print("Extracting technical terms...\n")
    terms = extract_technical_terms(sample_paragraph, top_n=15)
    
    print(f"Found {len(terms)} technical terms:")
    for i, term in enumerate(terms, 1):
        print(f"{i}. {term}")
