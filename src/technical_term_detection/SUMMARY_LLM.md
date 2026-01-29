# LLM-Based Technical Term Extraction System

## Overview

This system provides an advanced LLM-powered solution for extracting technical terms from academic text and automatically finding their definitions. It uses OpenAI's GPT models to understand context and provide accurate, domain-specific term extraction and definition generation.

## Architecture

### Components

```
technical_term_detection/
├── term_extractor_llm.py       # Main implementation
├── examples_llm.py              # Usage examples
├── integration.py               # Research paper integration
├── requirements_llm.txt         # Dependencies
└── README_LLM.md               # Detailed documentation
```

### Classes

#### 1. **LLMTermExtractor**
Extracts technical terms from paragraphs using LLM intelligence.

**Methods:**
- `extract_terms(paragraph, domain)` - Extract list of technical terms
- `extract_terms_with_context(paragraph, domain)` - Extract terms with usage context

**Example:**
```python
extractor = LLMTermExtractor(model="gpt-4o-mini")
terms = extractor.extract_terms(paragraph, domain="machine learning")
```

#### 2. **LLMTermDefinitionFinder**
Finds comprehensive definitions for technical terms.

**Methods:**
- `find_definition(term, domain, context)` - Find definition for single term
- `find_definitions_batch(terms, domain)` - Batch process multiple terms (efficient)

**Example:**
```python
finder = LLMTermDefinitionFinder(model="gpt-4o-mini")
definitions = finder.find_definitions_batch(
    ["neural network", "backpropagation"],
    domain="machine learning"
)
```

#### 3. **LLMTermExtractorPipeline**
Complete end-to-end pipeline combining extraction and definition finding.

**Methods:**
- `process_paragraph(paragraph, domain)` - Basic processing
- `process_paragraph_with_context(paragraph, domain)` - Enhanced processing with context

**Example:**
```python
pipeline = LLMTermExtractorPipeline(model="gpt-4o-mini")
result = pipeline.process_paragraph_with_context(
    paragraph, 
    domain="biology"
)
```

#### 4. **ResearchPaperTermExtractor** (integration.py)
Integration layer for research paper processing.

**Methods:**
- `extract_from_text(text, domain)` - Process single text block
- `extract_from_paper_sections(sections, domain)` - Process multiple sections
- `extract_from_abstract(abstract, domain)` - Process abstract specifically
- `create_glossary(terms_data, format)` - Generate glossary (markdown/html/text)

## Quick Start

### 1. Installation

```bash
cd technical_term_detection
pip install -r requirements_llm.txt
```

### 2. Set API Key

```bash
export OPENAI_API_KEY='your-api-key-here'
```

### 3. Run Examples

```bash
# Run all examples
python examples_llm.py

# Run the demo with sample paragraph
python term_extractor_llm.py

# Run integration example
python integration.py
```

## Usage Patterns

### Pattern 1: Quick Term Extraction

```python
from term_extractor_llm import LLMTermExtractor

extractor = LLMTermExtractor()
terms = extractor.extract_terms(
    "Deep learning models use neural networks for feature extraction.",
    domain="machine learning"
)
print(terms)  # ['deep learning', 'neural networks', 'feature extraction']
```

### Pattern 2: Complete Analysis

```python
from term_extractor_llm import LLMTermExtractorPipeline

pipeline = LLMTermExtractorPipeline()
result = pipeline.process_paragraph_with_context(
    paragraph,
    domain="computer science"
)

# Access results
for term_info in result['enriched_terms']:
    print(f"{term_info['term']}: {term_info['definition']}")
    print(f"Synonyms: {term_info['synonyms']}")
    print(f"Related: {term_info['related_terms']}")
```

### Pattern 3: Research Paper Processing

```python
from integration import ResearchPaperTermExtractor

extractor = ResearchPaperTermExtractor()

# Process multiple sections
sections = {
    "abstract": "...",
    "introduction": "...",
    "methodology": "..."
}

results = extractor.extract_from_paper_sections(
    sections,
    domain="biology"
)

# Create glossary
all_terms = []
for section_terms in results.values():
    all_terms.extend(section_terms)

glossary = extractor.create_glossary(all_terms, format="markdown")
```

## Output Format

### Basic Extraction
```json
["term1", "term2", "term3"]
```

### With Context
```json
[
  {
    "term": "neural network",
    "context": "used for image classification"
  }
]
```

### Complete Analysis
```json
{
  "paragraph": "...",
  "domain": "machine learning",
  "total_terms": 5,
  "enriched_terms": [
    {
      "term": "deep neural networks",
      "context": "revolutionized computer vision",
      "definition": "A class of neural networks with multiple hidden layers...",
      "domain_specific": "Machine Learning",
      "synonyms": ["DNN", "deep learning models"],
      "related_terms": ["CNNs", "RNNs", "transformers"]
    }
  ]
}
```

## Configuration

### Model Selection

- **gpt-4o-mini** (recommended) - Cost-effective, fast, accurate
- **gpt-4** - More powerful, higher cost
- **gpt-3.5-turbo** - Faster, lower accuracy

### Domain Options

Specify the domain for better accuracy:
- `"machine learning"`
- `"computer science"`
- `"biology"`
- `"physics"`
- `"chemistry"`
- `"medicine"`
- `"mathematics"`
- `"general"` (default)

### Temperature Setting

The system uses `temperature=0.3` for:
- Consistent results
- Focused output
- Reduced randomness

## API Costs (OpenAI)

Using **gpt-4o-mini**:
- Input: ~$0.15 per 1M tokens
- Output: ~$0.60 per 1M tokens
- **Typical paragraph**: $0.001 - $0.01 per request

### Cost Optimization Tips

1. Use `find_definitions_batch()` instead of individual calls
2. Process longer paragraphs (combine short ones)
3. Use `gpt-4o-mini` instead of `gpt-4`
4. Cache results for repeated terms

## Advantages

### vs KeyBERT
- ✅ Better context understanding
- ✅ Built-in definition generation
- ✅ Domain-aware extraction
- ✅ Multi-word term handling
- ❌ Requires API (cost)
- ❌ Needs internet

### vs SciSpacy
- ✅ Works across all domains
- ✅ Provides definitions automatically
- ✅ No model download/setup
- ✅ Better for multi-word terms
- ❌ Not free
- ❌ API-dependent

## Use Cases

### 1. Research Paper Analysis
```python
# Extract key terms from abstract
result = extractor.extract_from_abstract(abstract, domain="biology")
```

### 2. Educational Content
```python
# Create glossary for students
glossary = extractor.create_glossary(terms, format="html")
```

### 3. Literature Review
```python
# Extract terms from multiple papers
for paper in papers:
    terms = extractor.extract_from_text(paper.text, paper.domain)
```

### 4. Automated Documentation
```python
# Generate term definitions for technical docs
terms = ["API", "REST", "GraphQL"]
definitions = finder.find_definitions_batch(terms, "computer science")
```

## Error Handling

```python
try:
    result = pipeline.process_paragraph(paragraph, domain="physics")
except ValueError as e:
    # API key not configured
    print(f"Config error: {e}")
except Exception as e:
    # API error, rate limit, etc.
    print(f"Processing error: {e}")
```

## Integration with Existing Project

The term extractor can be integrated with the Research Paper Assistant:

```python
# In your metadata extraction pipeline
from technical_term_detection.integration import ResearchPaperTermExtractor

# After extracting text from PDF
term_extractor = ResearchPaperTermExtractor()
terms_data = term_extractor.extract_from_abstract(
    extracted_metadata['abstract'],
    domain=extracted_metadata.get('field', 'general')
)

# Add to metadata
extracted_metadata['technical_terms'] = terms_data
```

## Testing

```bash
# Run main demo
python term_extractor_llm.py

# Run all examples (interactive)
python examples_llm.py

# Run integration test
python integration.py
```

## Files Created

1. **term_extractor_llm.py** - Main implementation (450+ lines)
   - LLMTermExtractor class
   - LLMTermDefinitionFinder class
   - LLMTermExtractorPipeline class
   - Demo function

2. **examples_llm.py** - 5 comprehensive examples (300+ lines)
   - Basic extraction
   - Context extraction
   - Definition finding
   - Complete pipeline
   - Custom domains

3. **integration.py** - Research paper integration (250+ lines)
   - ResearchPaperTermExtractor class
   - Glossary generation (markdown/html/text)
   - Multi-section processing

4. **requirements_llm.txt** - Dependencies
   - openai>=1.12.0
   - python-dotenv>=1.0.0

5. **README_LLM.md** - Comprehensive documentation

## Next Steps

1. **Set up API key:**
   ```bash
   export OPENAI_API_KEY='your-key'
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements_llm.txt
   ```

3. **Run examples:**
   ```bash
   python term_extractor_llm.py
   ```

4. **Integrate with your workflow:**
   - Import the classes you need
   - Process your paragraphs/papers
   - Generate glossaries

## Support

For issues or questions:
1. Check README_LLM.md for detailed documentation
2. Review examples_llm.py for usage patterns
3. Ensure OPENAI_API_KEY is set correctly
4. Verify internet connectivity and API credits

## Future Enhancements

- [ ] Support for local LLMs (Ollama, Llama)
- [ ] Term caching to reduce costs
- [ ] Parallel processing for multiple paragraphs
- [ ] Export to additional formats (PDF, DOCX)
- [ ] Integration with vector databases
- [ ] Batch processing CLI tool
