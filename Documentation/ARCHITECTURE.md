# Architecture Documentation

## System Overview

The Research Paper Metadata Extractor is a **modular, deterministic pipeline** that extracts structured metadata from PDF research papers using a combination of rule-based heuristics and LLM inference.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        INPUT: PDF File                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   1. TEXT EXTRACTION NODE                       │
│                   (src/text_extraction.py)                      │
│                                                                 │
│  • Uses unstructured library with hi-res strategy              │
│  • Extracts text blocks with metadata                          │
│  • Captures: text, page number, element type                   │
│                                                                 │
│  Output: List[TextBlock]                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                2. SECTION DETECTION NODE                        │
│                (src/section_detection.py)                       │
│                                                                 │
│  HEURISTIC RULES (NO LLM):                                     │
│  • Element type = Title                                        │
│  • Short text (1-8 words)                                      │
│  • Contains section keywords                                   │
│  • Matches numbered patterns (1., 1.1, I., etc.)              │
│  • Capitalization patterns                                     │
│  • Confidence scoring system                                   │
│                                                                 │
│  Output: List[SectionCandidate]                                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                ▼                         ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│  3. TITLE EXTRACTION     │  │  4. ABSTRACT EXTRACTION  │
│     (src/graph.py)       │  │  (src/abstract_extraction)│
│                          │  │                          │
│  • Look for Title type   │  │  • Find "Abstract"       │
│  • First substantial     │  │  • Extract until first   │
│    text block            │  │    section               │
│                          │  │  • Clean formatting      │
│  Output: str (title)     │  │  Output: str (abstract)  │
└────────────┬─────────────┘  └────────────┬─────────────┘
             │                             │
             └────────────┬────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              5. SECTION NORMALIZATION NODE                      │
│                 (src/normalization.py)                          │
│                                                                 │
│  CANONICAL SECTIONS:                                            │
│  • Introduction      • Methodology    • Discussion             │
│  • Related Work      • Experiments    • Limitations            │
│  • Background        • Results        • Conclusion             │
│                                                                 │
│  MAPPING PROCESS:                                              │
│  • Remove numbering (1., I., etc.)                             │
│  • Lowercase and clean                                         │
│  • Regex pattern matching                                      │
│  • Keep original + normalized                                  │
│                                                                 │
│  Output: List[SectionMetadata]                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   6. LLM INFERENCE NODE                         │
│                   (src/llm_inference.py)                        │
│                                                                 │
│  ONE LLM CALL TO GROQ:                                         │
│                                                                 │
│  INPUT (strict):                                               │
│  • Title                                                       │
│  • Abstract                                                    │
│  • Section names (normalized)                                  │
│                                                                 │
│  OUTPUT (PydanticOutputParser):                                │
│  • paper_type: Survey, System, Theoretical, Empirical, etc.   │
│  • difficulty: easy, medium, hard                              │
│  • math_heavy: boolean                                         │
│  • suggested_focus_sections: list[str]                         │
│                                                                 │
│  Model: llama-3.3-70b-versatile (default)                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│               7. FINALIZATION NODE                              │
│                  (src/graph.py)                                 │
│                                                                 │
│  Assembles final PaperMetadata object:                         │
│  {                                                              │
│    title: str,                                                 │
│    abstract: str,                                              │
│    sections: List[SectionMetadata],                            │
│    inference: PaperInference                                   │
│  }                                                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│               OUTPUT: PaperMetadata (Pydantic)                  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### 1. **models.py**
- Defines Pydantic v2 schemas
- No logic, pure data structures
- Enforces type safety

### 2. **text_extraction.py**
- PDF parsing using `unstructured`
- Layout-aware extraction
- Returns structured TextBlock objects

### 3. **section_detection.py**
- **100% rule-based** (no LLM)
- Confidence scoring (0-1)
- Multiple heuristic rules combined

### 4. **abstract_extraction.py**
- Locates "Abstract" keyword
- Determines boundaries
- Cleans formatting artifacts

### 5. **normalization.py**
- Regex-based pattern matching
- Maps to 9 canonical sections
- Preserves original names

### 6. **llm_inference.py**
- **Single LLM call** (efficiency)
- Structured output with PydanticOutputParser
- Groq for fast inference

### 7. **graph.py**
- LangGraph orchestration
- TypedDict state management
- Error handling at each node

### 8. **extractor.py**
- Main entry point
- Simple API: `extract_paper_metadata(pdf_path)`
- Handles API key management

## Design Decisions

### Why LangGraph?
- **Modular**: Each step is testable in isolation
- **Observable**: Clear execution flow
- **Extensible**: Easy to add new nodes
- **State management**: Typed state across pipeline

### Why Heuristics for Sections?
- **Deterministic**: No LLM variance
- **Fast**: No API calls for basic detection
- **Reliable**: Rule-based is predictable
- **Cost-effective**: Reserve LLM for inference only

### Why Single LLM Call?
- **Efficiency**: Minimizes API costs
- **Latency**: One round-trip only
- **Simplicity**: Easier to debug
- **Structured output**: Pydantic validation

### Why Normalization?
- **Consistency**: Standard section names across papers
- **Analysis**: Easier to compare papers
- **Flexibility**: Original name preserved

## Data Flow

```
PDF bytes
  → TextBlocks (text + metadata)
    → SectionCandidates (detected headings)
      → Title (string)
      → Abstract (string)
      → SectionMetadata[] (original + normalized)
        → LLM Input (title, abstract, section names)
          → PaperInference (type, difficulty, etc.)
            → PaperMetadata (final output)
```

## Error Handling Strategy

Each node includes:
- Try-catch blocks
- Graceful fallbacks
- Error state propagation
- Warning logs (not failures)

Example: If abstract not found, use "No abstract found." and continue.

## Extension Points

To extend the system:

1. **Add new canonical sections**: Edit `CANONICAL_SECTIONS` in normalization.py
2. **Improve detection**: Add rules in section_detection.py
3. **Change LLM**: Modify `DEFAULT_MODEL` in llm_inference.py
4. **Add preprocessing**: Insert node before text_extraction
5. **Post-processing**: Add node after finalization

## Performance Characteristics

- **Time complexity**: O(n) where n = number of text blocks
- **Space complexity**: O(n) for storing blocks
- **LLM calls**: Exactly 1 per document
- **Deterministic**: Same input → same output (except LLM variance)

## Testing Strategy

- **Unit tests**: Each module independently
- **Integration tests**: Full pipeline
- **Mocking**: Can mock LLM for deterministic tests
- **Validation**: Pydantic enforces schema

## Future Enhancements (Not Implemented)

Potential additions (out of scope for current version):
- Figure/table detection
- Citation extraction
- Author metadata
- Equation extraction
- Reference parsing
