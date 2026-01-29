# Technical Term Detection

Extracts domain-specific and technical terms from academic/research text using lightweight local NLP models.

## Features

- ✅ No LLM API calls required
- ✅ Extracts noun phrases and technical terms
- ✅ Removes common English words
- ✅ Deduplicates results
- ✅ Lightweight and fast

## Implementations

### 1. KeyBERT Approach (Recommended)
**File:** `term_extractor.py`

Uses KeyBERT with `all-MiniLM-L6-v2` model for semantic keyword extraction combined with spaCy for noun phrase detection.

**Pros:**
- Works across all domains
- Fast and accurate
- Good for general academic text

### 2. SciSpacy Approach
**File:** `term_extractor_scispacy.py`

Uses SciSpacy's scientific/biomedical language models.

**Pros:**
- Optimized for scientific text
- Better for STEM domains
- Recognizes scientific entities

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm

# Optional: For SciSpacy
pip install scispacy
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz
```

## Usage

### KeyBERT Method

```python
from term_extractor import extract_technical_terms

paragraph = """
Your academic or research text here...
"""

terms = extract_technical_terms(paragraph, top_n=15)
print(terms)
```

### SciSpacy Method

```python
from term_extractor_scispacy import extract_technical_terms

paragraph = """
Your scientific text here...
"""

terms = extract_technical_terms(paragraph, top_n=15)
print(terms)
```

## Function Signature

```python
def extract_technical_terms(
    paragraph: str, 
    top_n: int = 20,
    diversity: float = 0.5  # KeyBERT only
) -> List[str]
```

**Parameters:**
- `paragraph`: Input text (string)
- `top_n`: Maximum number of terms to return
- `diversity`: (KeyBERT only) Control term diversity (0-1)

**Returns:**
- List of technical terms (deduplicated)

## Examples

Run the example:
```bash
python term_extractor.py
```

## Notes

- Models are lazy-loaded on first use
- Both methods preserve multi-word technical phrases
- Results are ordered by relevance/importance
