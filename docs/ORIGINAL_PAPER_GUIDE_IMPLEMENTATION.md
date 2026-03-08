# Original Paper Reading Guide - Implementation Summary

## Overview

The research paper assistant now automatically generates **Three-Pass Method reading guides** for papers categorized as **ORIGINAL_RESEARCH**. This helps students and researchers efficiently read and understand original research papers.

## Workflow

```
PDF → Extraction → Categorizer → [Decision Point]
                                      ↓
                    if category == ORIGINAL_RESEARCH (and no query)
                                      ↓
                            Original Paper Guide
                                      ↓
                            Save to JSON file
```

## Implementation Details

### Files Modified

1. **backend/rag/prompts.py**
   - Added `original_paper_guide_prompt()` function
   - Implements detailed Three-Pass Method prompt with structured JSON output
   - Includes metadata: title, abstract, sections, figures, tables

2. **backend/rag/states.py**
   - Added `reading_guide` field to store generated guide
   - Added `guide_file_path` field to store path to saved JSON file

3. **backend/rag/graph.py**
   - Added `original_paper_guide_node()` function
   - Updated `route_after_categorizer()` to check for ORIGINAL_RESEARCH category
   - Wired the new node into the LangGraph pipeline
   - Uses **qwen/qwen-2.5-32b-instruct** model from Groq

4. **backend/examples/original_paper_guide_example.py** (NEW)
   - Complete example demonstrating guide generation
   - Shows how to access and display guide results

### Routing Logic

The categorizer now routes as follows:

```python
if category == "ORIGINAL_RESEARCH" and no query:
    → original_paper_guide (generate reading guide)
elif query exists:
    → retriever → qa (Q&A mode)
else:
    → summarizer (summary mode)
```

## Guide Output Format

The generated guide follows this JSON structure:

```json
{
  "paper_title": "...",
  "reading_strategy": {
    "method": "three_pass_method",
    "paper_type": "original_research",
    "estimated_total_time": "1.5-2.5 hours"
  },
  "pass1_quick_scan": {
    "goal": "Understand the main problem, contribution, and relevance",
    "estimated_time": "5-10 minutes",
    "steps": [
      {
        "step_number": 1,
        "section_to_read": ["Title", "Abstract"],
        "objective": "Identify the problem and main idea",
        "questions_to_answer": [...],
        "expected_output": "..."
      },
      ...
    ]
  },
  "pass2_method_understanding": {
    "goal": "Understand the proposed method and experimental setup",
    "estimated_time": "20-40 minutes",
    "steps": [...]
  },
  "pass3_deep_analysis": {
    "goal": "Critically analyze technical details and limitations",
    "estimated_time": "1-2 hours",
    "steps": [...]
  },
  "final_user_task": {
    "summary_task": "Write a 5 sentence summary...",
    "reflection_questions": [...]
  }
}
```

## Usage

### Basic Usage

```python
from backend.run import PaperAnalysisPipeline

pipeline = PaperAnalysisPipeline()

# Run on an original research paper (no query = guide mode)
result = pipeline.run(pdf_path="path/to/paper.pdf")

# Check if guide was generated
if result.get('reading_guide'):
    print(f"Guide saved to: {result['guide_file_path']}")
    guide = result['reading_guide']
    # Access guide sections
    pass1 = guide['pass1_quick_scan']
    pass2 = guide['pass2_method_understanding']
    pass3 = guide['pass3_deep_analysis']
```

### CLI Usage

```bash
# Generate guide for original research paper
python backend/run.py path/to/original_paper.pdf

# The guide will be automatically saved to:
# output/<document_id>_guide.json
```

### Example Script

```bash
# Run the example demonstrating guide generation
python backend/examples/original_paper_guide_example.py
```

## Three-Pass Method

The generated guide follows the proven **Three-Pass Method** for reading research papers:

### Pass 1 - Quick Scan (5-10 minutes)
- Read: Title, Abstract, Introduction, Conclusion
- Goal: Understand main problem and contribution
- Decision: Is the paper worth deeper reading?

### Pass 2 - Method Understanding (20-40 minutes)
- Read: Method, Experiments, Results
- Study: Architecture figures and result tables
- Goal: Understand how the method works and how it's evaluated

### Pass 3 - Deep Analysis (1-2 hours)
- Read: All technical details, equations, algorithms
- Study: Ablation studies, limitations, discussion
- Goal: Critical analysis and deep understanding

## Key Features

✅ **Automatic Generation**: Guide is generated automatically for ORIGINAL_RESEARCH papers
✅ **Structured Format**: JSON format for easy parsing and display
✅ **Context-Aware**: Adapts to actual sections in the paper
✅ **Metadata-Rich**: Uses figures, tables, and section info to tailor guide
✅ **Student-Friendly**: Designed to help students learn effective reading strategies
✅ **Saved Output**: Guide saved to `output/<document_id>_guide.json`

## Model Configuration

- **Model**: qwen/qwen-2.5-32b-instruct (Groq)
- **Temperature**: 0.1 (low temperature for consistent structure)
- **Output Format**: JSON mode for structured guide generation

## Integration with Existing Workflow

The guide generation integrates seamlessly with the existing pipeline:

- **Does NOT break existing functionality**: Q&A and summarization still work
- **Automatic routing**: Based on category and query presence
- **File persistence**: Guides saved alongside other extraction artifacts
- **State management**: Fully integrated with LangGraph state

## Output Location

All guides are saved in the `output/` directory with naming convention:
```
output/<document_id>_guide.json
```

Where `<document_id>` is the unique identifier assigned during extraction.

## Testing

Run the example to test:
```bash
python backend/examples/original_paper_guide_example.py
```

The example will:
1. Check for Groq API key
2. Process a sample paper
3. Display guide summary if generated
4. Show guide file location

## Notes

- Guide is only generated when:
  - Paper category is `ORIGINAL_RESEARCH`
  - No query is provided (not in Q&A mode)
- If paper is not ORIGINAL_RESEARCH, the pipeline generates a summary instead
- The guide adapts to actual sections found in the paper
- All section references are customized to match the paper structure

## Future Enhancements

Potential improvements:
- Support for other paper categories (Survey, Theoretical, etc.)
- Interactive guide viewer/UI
- Progress tracking as user completes each step
- Integration with note-taking tools
- Customizable reading strategies based on user level (beginner/advanced)
