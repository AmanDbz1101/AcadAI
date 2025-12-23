# Research Paper Metadata Extractor
# Version 1.0.0 - Initial Release

## Project Structure

```
Research Paper Assistant/
├── src/                              # Core extraction pipeline
│   ├── __init__.py                  # Package initialization
│   ├── models.py                    # Pydantic data models
│   ├── text_extraction.py           # PDF parsing (unstructured)
│   ├── section_detection.py         # Heuristic section detection
│   ├── normalization.py             # Section name normalization
│   ├── abstract_extraction.py       # Abstract extraction logic
│   ├── llm_inference.py             # Groq LLM inference
│   ├── graph.py                     # LangGraph orchestration
│   └── extractor.py                 # Main entry point
│
├── input/                            # Sample PDFs for testing
│   ├── MemGPT.pdf
│   ├── sample_1.pdf
│   └── sample_2.pdf
│
├── output/                           # Output directory for results
│   ├── figures/
│   ├── formulas/
│   └── page_images/
│
├── Documentation Files
│   ├── README_METADATA_EXTRACTOR.md  # Complete user guide
│   ├── QUICKSTART.md                 # 3-step quick start
│   ├── ARCHITECTURE.md               # Technical architecture
│   └── IMPLEMENTATION_SUMMARY.md     # What was delivered
│
├── Usage & Testing
│   ├── example_usage.py              # 6 usage examples
│   ├── test_extractor.py             # Test suite (5 tests)
│   └── .env.example                  # Environment template
│
└── Configuration
    └── requirements.txt              # Python dependencies
```

## File Descriptions

### Core Pipeline (`src/`)

**models.py** (61 lines)
- Pydantic v2 models for structured data
- SectionMetadata, PaperInference, PaperMetadata
- Type-safe schema definitions

**text_extraction.py** (91 lines)
- PDFTextExtractor class
- Uses unstructured library with hi-res strategy
- Returns TextBlock objects with metadata

**section_detection.py** (208 lines)
- SectionDetector class
- 8 heuristic rules for heading detection
- Confidence scoring system (0-1)
- Pattern matching for numbered sections

**normalization.py** (140 lines)
- SectionNormalizer class
- Maps to 9 canonical section labels
- Regex-based pattern matching
- Preserves original + normalized names

**abstract_extraction.py** (116 lines)
- AbstractExtractor class
- Keyword-based detection
- Boundary analysis using section candidates
- Formatting cleanup

**llm_inference.py** (117 lines)
- PaperInferenceEngine class
- Single Groq LLM call per paper
- PydanticOutputParser for structured output
- Infers type, difficulty, math_heavy, focus_sections

**graph.py** (284 lines)
- MetadataExtractionGraph class
- LangGraph orchestration with 7 nodes
- TypedDict state management
- Error handling per node

**extractor.py** (110 lines)
- Main entry point: extract_paper_metadata()
- Pretty-print function: extract_and_display()
- Command-line interface
- API key management

### Supporting Files

**example_usage.py** (133 lines)
- 6 comprehensive examples:
  1. Basic usage
  2. Detailed section analysis
  3. Explicit API key
  4. Batch processing
  5. JSON export
  6. Error handling

**test_extractor.py** (158 lines)
- 5 test functions:
  1. Import tests
  2. Pydantic model tests
  3. Section normalizer tests
  4. Section detector tests
  5. LangGraph structure tests
- All tests passing ✅

### Documentation

**README_METADATA_EXTRACTOR.md** (300+ lines)
- Complete user guide
- Installation instructions
- API documentation
- Usage examples
- Troubleshooting

**QUICKSTART.md** (80+ lines)
- 3-step quick start
- What you get
- Test your setup
- Common issues

**ARCHITECTURE.md** (250+ lines)
- ASCII architecture diagram
- Component responsibilities
- Design decisions
- Data flow
- Extension points

**IMPLEMENTATION_SUMMARY.md** (200+ lines)
- What was delivered
- Requirements checklist
- Code statistics
- Validation results

### Configuration

**.env.example**
- Environment variable template
- GROQ_API_KEY placeholder

**requirements.txt**
- Core dependencies:
  - unstructured[pdf]
  - langchain-groq
  - langchain-core
  - langgraph
  - pydantic>=2.0.0
  - python-dotenv

## Version History

### v1.0.0 - Initial Release (December 20, 2025)

**Features:**
- ✅ Complete metadata extraction pipeline
- ✅ Heuristic-based section detection (no LLM)
- ✅ Section name normalization (9 canonical labels)
- ✅ Single LLM call for paper inference
- ✅ LangGraph orchestration with 7 nodes
- ✅ Pydantic v2 structured outputs
- ✅ Comprehensive error handling
- ✅ Full documentation suite
- ✅ Usage examples and tests

**Tech Stack:**
- Python 3.10+
- unstructured (PDF parsing)
- langchain-groq (LLM inference)
- LangGraph (orchestration)
- Pydantic v2 (validation)

**Metrics:**
- 8 Python modules
- ~1,500 lines of code
- 5 tests (all passing)
- 4 documentation files
- 1 LLM call per paper

## Quick Reference

### Installation
```bash
pip install -r requirements.txt
export GROQ_API_KEY='your_key_here'
```

### Basic Usage
```python
from src.extractor import extract_paper_metadata
metadata = extract_paper_metadata("paper.pdf")
```

### Command Line
```bash
python -m src.extractor paper.pdf
```

### Run Tests
```bash
python test_extractor.py
```

## Dependencies

Required:
- unstructured[pdf] - PDF parsing
- langchain-groq - Groq LLM integration
- langchain-core - LangChain utilities
- langgraph - State graph orchestration
- pydantic>=2.0.0 - Data validation
- python-dotenv - Environment variables

## License

[Add your license]

## Author

Generated for Research Paper Assistant project
December 20, 2025
