# LLM-Based Technical Term Extraction and Definition

This module provides an advanced LLM-powered system for extracting technical terms from academic text and finding their definitions.

## Features

### 1. **LLMTermExtractor**
- Extracts technical terms from paragraphs using LLM intelligence
- Supports domain-specific extraction (e.g., "machine learning", "biology", "physics")
- Can extract terms with contextual usage information
- Returns structured JSON output

### 2. **LLMTermDefinitionFinder**
- Finds comprehensive definitions for technical terms
- Provides synonyms and related terms
- Supports both single-term and batch processing
- Domain-aware definitions

### 3. **LLMTermExtractorPipeline**
- Complete end-to-end pipeline
- Extracts terms and finds definitions in one go
- Two processing modes:
  - Basic: Extract terms → Find definitions
  - Enhanced: Extract terms with context → Find enriched definitions

## Installation

### Install Required Packages

```bash
pip install -r requirements_llm.txt
```

### Set Up OpenAI API Key

```bash
# Linux/Mac
export OPENAI_API_KEY='your-api-key-here'

# Windows (PowerShell)
$env:OPENAI_API_KEY='your-api-key-here'

# Or create a .env file
echo "OPENAI_API_KEY=your-api-key-here" > .env
```

## Usage

### Basic Usage

```python
from term_extractor_llm import LLMTermExtractorPipeline

# Initialize the pipeline
pipeline = LLMTermExtractorPipeline(model="gpt-4o-mini")

# Your paragraph
paragraph = """
Deep neural networks have revolutionized computer vision tasks through 
convolutional architectures. The backpropagation algorithm enables efficient 
training of multi-layer networks.
"""

# Process with context-aware extraction
result = pipeline.process_paragraph_with_context(
    paragraph, 
    domain="machine learning"
)

# Access results
print(f"Found {result['total_terms']} technical terms")
for term_info in result['enriched_terms']:
    print(f"Term: {term_info['term']}")
    print(f"Definition: {term_info['definition']}")
    print(f"Synonyms: {term_info['synonyms']}")
    print()
```

### Extract Terms Only

```python
from term_extractor_llm import LLMTermExtractor

extractor = LLMTermExtractor(model="gpt-4o-mini")

# Simple extraction
terms = extractor.extract_terms(paragraph, domain="biology")
print(f"Terms: {terms}")

# Extraction with context
terms_with_context = extractor.extract_terms_with_context(paragraph, domain="biology")
for item in terms_with_context:
    print(f"{item['term']}: {item['context']}")
```

### Find Definitions Only

```python
from term_extractor_llm import LLMTermDefinitionFinder

finder = LLMTermDefinitionFinder(model="gpt-4o-mini")

# Single term
definition = finder.find_definition("neural network", domain="machine learning")
print(definition['definition'])

# Multiple terms (batch processing - more efficient)
terms = ["neural network", "backpropagation", "convolution"]
definitions = finder.find_definitions_batch(terms, domain="machine learning")
for def_info in definitions:
    print(f"{def_info['term']}: {def_info['definition']}")
```

### Run the Demo

```bash
cd technical_term_detection
python term_extractor_llm.py
```

This will:
1. Extract technical terms from a sample machine learning paragraph
2. Find definitions for each term
3. Display results with synonyms and related terms
4. Save output to `term_extraction_results.json`

## Output Format

### Enhanced Processing Output

```json
{
  "paragraph": "...",
  "domain": "machine learning",
  "total_terms": 5,
  "enriched_terms": [
    {
      "term": "deep neural networks",
      "context": "revolutionized computer vision tasks",
      "definition": "A class of neural networks with multiple hidden layers...",
      "domain_specific": "Machine Learning",
      "synonyms": ["DNN", "deep learning models"],
      "related_terms": ["artificial neural networks", "CNNs", "RNNs"]
    }
  ]
}
```

## Configuration

### Model Selection

```python
# Cost-effective (recommended)
pipeline = LLMTermExtractorPipeline(model="gpt-4o-mini")

# More powerful
pipeline = LLMTermExtractorPipeline(model="gpt-4")

# Alternative providers (requires additional setup)
pipeline = LLMTermExtractorPipeline(model="gpt-3.5-turbo")
```

### Domain Options

Common domains:
- `"machine learning"`
- `"computer science"`
- `"biology"`
- `"physics"`
- `"chemistry"`
- `"medicine"`
- `"mathematics"`
- `"general"` (default)

## API Costs

Using OpenAI's `gpt-4o-mini` (recommended):
- ~$0.15 per 1M input tokens
- ~$0.60 per 1M output tokens
- Typical paragraph processing: $0.001 - $0.01 per request

## Advantages over Traditional Methods

1. **Context-Aware**: Understands semantic meaning, not just patterns
2. **Domain-Specific**: Tailors extraction to specific fields
3. **Comprehensive Definitions**: Provides detailed, accurate definitions
4. **No Training Required**: Works immediately without model training
5. **Multi-Word Terms**: Naturally handles complex technical phrases
6. **Explanation Capability**: Can provide context for term usage

## Comparison with KeyBERT/SciSpacy

| Feature | LLM-Based | KeyBERT | SciSpacy |
|---------|-----------|---------|----------|
| Context Understanding | ✅ Excellent | ⚠️ Limited | ⚠️ Limited |
| Definition Generation | ✅ Built-in | ❌ No | ❌ No |
| Domain Awareness | ✅ Yes | ⚠️ Limited | ✅ Yes (Science) |
| Setup Complexity | ⚠️ API Key | ✅ Simple | ⚠️ Model Download |
| Cost | ⚠️ Per-use | ✅ Free | ✅ Free |
| Offline Use | ❌ No | ✅ Yes | ✅ Yes |
| Accuracy | ✅ Very High | ⚠️ Good | ✅ High (Science) |

## Error Handling

The module includes robust error handling:

```python
try:
    result = pipeline.process_paragraph(paragraph, domain="biology")
except ValueError as e:
    print(f"Configuration error: {e}")
except Exception as e:
    print(f"Processing error: {e}")
```

## Environment Variables

```bash
# Required
OPENAI_API_KEY=your-key-here

# Optional
OPENAI_ORG_ID=your-org-id  # If using organization
```

## Troubleshooting

### "API key not found" error
- Ensure `OPENAI_API_KEY` environment variable is set
- Or pass `api_key` parameter directly

### Rate limiting errors
- The module uses reasonable temperature settings (0.3)
- Consider adding retry logic for production use

### JSON parsing errors
- The module uses `response_format={"type": "json_object"}` for structured output
- Handles various response formats gracefully

## Future Enhancements

- [ ] Support for local LLMs (Ollama, LLaMA)
- [ ] Caching layer for repeated terms
- [ ] Batch processing for multiple paragraphs
- [ ] Export to various formats (CSV, PDF, Markdown)
- [ ] Integration with research paper metadata extraction

## License

Same as parent project.

## Contributing

Contributions welcome! Please ensure:
1. Code follows existing style
2. Add tests for new features
3. Update documentation
