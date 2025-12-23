# Quick Start Guide - Research Paper Metadata Extractor

## 🚀 Get Started in 3 Steps

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Set Up API Key

```bash
# Copy the example env file
cp .env.example .env

# Edit .env and add your Groq API key
# Get your key from: https://console.groq.com/keys
```

### Step 3: Run the Extractor

```python
from src.extractor import extract_paper_metadata

# Extract metadata from a PDF
metadata = extract_paper_metadata("path/to/your/paper.pdf")

# Print results
print(f"Title: {metadata.title}")
print(f"Type: {metadata.inference.paper_type}")
print(f"Difficulty: {metadata.inference.difficulty}")
```

Or use the command line:

```bash
python -m src.extractor path/to/your/paper.pdf
```

## 📋 What You Get

The extractor returns a structured `PaperMetadata` object with:

```python
{
  "title": "Paper title",
  "abstract": "Paper abstract...",
  "sections": [
    {
      "original_name": "1. Introduction",
      "normalized_name": "Introduction",
      "page_start": 1
    },
    # ... more sections
  ],
  "inference": {
    "paper_type": "Survey",
    "difficulty": "medium",
    "math_heavy": false,
    "suggested_focus_sections": ["Introduction", "Results"]
  }
}
```

## 🧪 Test Your Setup

Run the test suite to verify everything works:

```bash
python test_extractor.py
```

## 📚 More Examples

Check [example_usage.py](example_usage.py) for:
- Batch processing multiple PDFs
- Exporting to JSON
- Error handling
- Advanced usage patterns

## 🔧 Troubleshooting

### "Groq API key not provided"
Make sure you've set `GROQ_API_KEY` in your `.env` file or export it:
```bash
export GROQ_API_KEY='your_key_here'
```

### "PDF file not found"
Check that the PDF path is correct and the file exists.

### Import errors
Make sure all dependencies are installed:
```bash
pip install -r requirements.txt
```

## 📖 Full Documentation

See [README_METADATA_EXTRACTOR.md](README_METADATA_EXTRACTOR.md) for complete documentation.
