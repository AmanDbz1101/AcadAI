# Research Paper Metadata Extractor

A production-ready metadata extraction pipeline for research papers using LangGraph orchestration and Groq LLM inference.

## 🎯 Overview

This system extracts structured metadata from PDF research papers, including:

- **Paper Title** - Automatically detected from document
- **Abstract** - Extracted with formatting cleanup
- **Section Structure** - Heuristic-based detection with normalization to canonical names
- **Paper Properties** - LLM-inferred type, difficulty, and focus sections

## 🏗️ Architecture

```
PDF Input → Text Extraction → Section Detection → Normalization 
         → LLM Inference → Structured Metadata (Pydantic)
```

### Pipeline Stages (LangGraph Nodes)

1. **Text Extraction** - Uses `unstructured` library to parse PDF with layout analysis
2. **Section Detection** - Rule-based heuristics (no LLM) detect headings
3. **Title Extraction** - Identifies paper title from document structure
4. **Abstract Extraction** - Locates and extracts abstract content
5. **Section Normalization** - Maps sections to canonical labels
6. **LLM Inference** - Single Groq call infers paper properties
7. **Finalization** - Assembles complete PaperMetadata object

## 🛠️ Tech Stack

- **Python 3.10+**
- **unstructured** - PDF parsing with layout analysis
- **LangGraph** - State graph orchestration
- **langchain-groq** - LLM inference
- **Pydantic v2** - Structured data validation

## 📦 Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Set Groq API key
export GROQ_API_KEY='your_groq_api_key_here'
```

## 🚀 Quick Start

### Basic Usage

```python
from src.extractor import extract_paper_metadata

# Extract metadata
metadata = extract_paper_metadata("path/to/paper.pdf")

# Access results
print(metadata.title)
print(metadata.inference.paper_type)
print(metadata.inference.difficulty)

# Iterate sections
for section in metadata.sections:
    print(f"{section.original_name} -> {section.normalized_name}")
```

### Command Line

```bash
python -m src.extractor path/to/paper.pdf
```

### Display Results

```python
from src.extractor import extract_and_display

extract_and_display("paper.pdf")
```

## 📊 Output Schema

### PaperMetadata

```python
class PaperMetadata(BaseModel):
    title: str
    abstract: str
    sections: list[SectionMetadata]
    inference: PaperInference
```

### SectionMetadata

```python
class SectionMetadata(BaseModel):
    original_name: str            # Section name as it appears
    normalized_name: str | None   # Canonical label (or None)
    page_start: int              # Starting page (1-indexed)
```

### PaperInference

```python
class PaperInference(BaseModel):
    paper_type: str                      # Survey, System, Theoretical, etc.
    difficulty: str                      # easy, medium, hard
    math_heavy: bool                     # Heavy mathematical content?
    suggested_focus_sections: list[str]  # Key sections to read
```

## 🔍 Features

### Section Detection (Heuristic-Based)

Uses multiple rules to detect section headings:

- Element type analysis (Title vs NarrativeText)
- Text length and format
- Keyword matching (Introduction, Methodology, etc.)
- Numbered section patterns (1., 1.1, I., etc.)
- Capitalization and punctuation patterns

### Section Normalization

Maps detected sections to canonical labels:

- Introduction
- Related Work
- Background
- Methodology
- Experiments
- Results
- Discussion
- Limitations
- Conclusion

Original names are preserved; normalized name may be `None` if no clear mapping.

### LLM Inference (Single Call)

One Groq API call infers:

- **paper_type**: Classification (Survey, System, Empirical, etc.)
- **difficulty**: Reading level (easy, medium, hard)
- **math_heavy**: Boolean flag for mathematical content
- **suggested_focus_sections**: 2-4 key sections

Input is strictly limited to: title, abstract, and section names.

## 📁 Project Structure

```
src/
├── __init__.py              # Package initialization
├── models.py                # Pydantic models
├── text_extraction.py       # PDF parsing with unstructured
├── section_detection.py     # Heuristic section detection
├── normalization.py         # Section name normalization
├── abstract_extraction.py   # Abstract extraction logic
├── llm_inference.py         # Groq LLM inference
├── graph.py                 # LangGraph orchestration
└── extractor.py            # Main entry point

example_usage.py             # Usage examples
requirements.txt             # Dependencies
```

## 🔧 Configuration

### Environment Variables

```bash
# Required
GROQ_API_KEY='your_groq_api_key'
```

### Custom Model

```python
from src.llm_inference import PaperInferenceEngine

engine = PaperInferenceEngine(
    model_name="llama-3.3-70b-versatile",  # or other Groq model
    api_key="your_key"
)
```

## 📝 Examples

See [example_usage.py](example_usage.py) for comprehensive examples:

- Basic extraction
- Detailed section analysis
- Batch processing
- JSON export
- Error handling

## 🧪 Testing

```python
from src.extractor import extract_paper_metadata

# Test extraction
metadata = extract_paper_metadata("test_paper.pdf")

assert metadata.title
assert metadata.abstract
assert len(metadata.sections) > 0
assert metadata.inference.paper_type in [
    "Survey", "System", "Theoretical", "Empirical", "Other"
]
```

## 🚫 Out of Scope

This extractor does **NOT** implement:

- Embeddings or vector databases
- RAG (Retrieval Augmented Generation)
- Document summarization
- Multi-agent systems
- Chunk storage

This is **metadata extraction only**, designed to be a component in larger systems.

## 🐛 Error Handling

The pipeline includes graceful error handling:

- Invalid PDF files
- Missing sections
- LLM inference failures (falls back to defaults)
- Missing abstracts

Errors are logged, and extraction continues with best-effort results.

## 📚 Dependencies

Core libraries:

- `unstructured[pdf]` - PDF parsing
- `langchain-groq` - Groq LLM integration
- `langchain-core` - LangChain utilities
- `langgraph` - State graph orchestration
- `pydantic>=2.0.0` - Data validation

## 🤝 Contributing

This is a self-contained extraction module. To extend:

1. Add new normalization rules in `normalization.py`
2. Enhance section detection heuristics in `section_detection.py`
3. Modify LLM prompt in `llm_inference.py`
4. Add new graph nodes in `graph.py`

## 📄 License

[Add your license here]

## 🙏 Acknowledgments

Built with:
- [Unstructured](https://unstructured.io/) - PDF parsing
- [LangGraph](https://github.com/langchain-ai/langgraph) - Orchestration
- [Groq](https://groq.com/) - Fast LLM inference
