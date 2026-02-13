# Section Hierarchy Detection Module

## Overview

The Section Hierarchy Detection module recovers the logical structure of research papers by detecting section headers, identifying main/subsections, and building a navigable hierarchical tree. This structure serves as the backbone for section-aware chunking, targeted retrieval, and reading guide generation.

## Features

- **Automatic Section Detection**: Identifies section headers using multiple signals:
  - Typography cues (font size, boldness)
  - Numbering patterns (1., 2.3, IV-B, etc.)
  - Keyword matching (Introduction, Methodology, etc.)

- **Hierarchical Structure**: Builds parent-child relationships between sections
  - Supports nested subsections up to 6 levels deep
  - Tracks section numbering and reading order
  - Calculates page ranges for each section

- **Rich Navigation API**: Query and traverse the section tree
  - Find sections by title or level
  - Get ancestors, descendants, and section paths
  - Navigate parent-child relationships

- **Confidence Scoring**: Estimates detection quality based on:
  - Presence of numbering
  - Hierarchy consistency
  - Section count reasonableness

## Architecture

### Core Components

1. **Models** ([section_hierarchy.py](../models/section_hierarchy.py))
   - `SectionNode`: Represents a single section with metadata
   - `SectionHierarchy`: Complete hierarchical structure with navigation methods
   - `SectionDetectionResult`: Detection results with timing and warnings

2. **Detector** ([section_detector.py](../app/processing/section_detector.py))
   - `SectionDetector`: Core detection logic
   - Extracts candidate headers from documents
   - Builds hierarchical relationships
   - Calculates confidence scores

3. **Pipeline** ([section_hierarchy_pipeline.py](../pipelines/section_hierarchy_pipeline.py))
   - `SectionHierarchyPipeline`: Orchestrates detection workflow
   - Processes both `ProcessedDocument` and `ValidatedDocument`
   - Provides save/load functionality for hierarchies

## Usage

### Basic Usage

```python
from backend.pipelines import SectionHierarchyPipeline
from backend.models import ProcessedDocument

# Initialize pipeline
pipeline = SectionHierarchyPipeline()

# Process a document
result = pipeline.process_from_processed_document(processed_doc)
hierarchy = result.hierarchy

# Access detected sections
print(f"Total sections: {hierarchy.total_sections}")
print(f"Max depth: {hierarchy.max_depth}")
print(f"Confidence: {hierarchy.confidence_score:.2f}")
```

### Navigation Examples

```python
# Get all top-level sections
level1_sections = hierarchy.get_sections_by_level(1)
for section in level1_sections:
    print(f"- {section.title} (Page {section.page_start})")

# Find sections by title
intro = hierarchy.find_sections_by_title("Introduction")[0]
print(f"Found: {intro.full_path}")

# Navigate hierarchy
children = hierarchy.get_children(intro.section_id)
parent = hierarchy.get_parent(some_section.section_id)
ancestors = hierarchy.get_ancestors(deep_section.section_id)
descendants = hierarchy.get_descendants(intro.section_id)

# Get section path from root
path = hierarchy.get_section_path(section_id)
for section in path:
    print(f"  {'  ' * (section.level - 1)}{section.title}")
```

### Saving and Loading

```python
from pathlib import Path

# Save hierarchy to JSON
output_path = Path("output/hierarchy.json")
pipeline.save_hierarchy(hierarchy, output_path)

# Load hierarchy from JSON
loaded_hierarchy = pipeline.load_hierarchy(output_path)
```

## Detection Methods

### From ProcessedDocument (Recommended)

Uses metadata already extracted by Docling:

```python
result = pipeline.process_from_processed_document(processed_doc, validated_doc)
```

**Advantages**:
- Higher accuracy (uses Docling's structure analysis)
- Faster (metadata already extracted)
- More reliable numbering and level detection

### From ValidatedDocument

Uses heuristic pattern matching on raw text:

```python
result = pipeline.process_from_validated_document(validated_doc)
```

**Use when**:
- Metadata extraction hasn't been performed
- You need section detection without full metadata

## Section Node Properties

Each `SectionNode` contains:

- **Identification**
  - `section_id`: Unique identifier
  - `title`: Clean section heading (without numbering)
  - `numbering`: Section number (e.g., "1.2.3", "IV-B")

- **Hierarchy**
  - `level`: Depth in hierarchy (1-6)
  - `parent_id`: Parent section ID
  - `child_section_ids`: List of child section IDs

- **Position**
  - `page_start`: Starting page number
  - `page_end`: Ending page number
  - `reading_order`: Sequential position in document

- **Typography** (optional)
  - `font_size`: Font size in points
  - `is_bold`: Whether heading is bold

## Numbering Patterns Supported

The detector recognizes various numbering schemes:

- **Decimal**: `1.`, `2.3`, `1.2.3`
- **Roman numerals**: `I.`, `IV.`, `II-A`
- **Letters**: `A.`, `B.1`, `C.2.1`
- **Mixed**: `1.2.a`, `IV-B.1`

## Section Keywords

Common section names automatically detected:

- Introduction, Abstract, Background
- Related Work, Literature Review
- Methodology, Methods, Approach
- Experiments, Evaluation, Results
- Discussion, Analysis, Findings
- Conclusion, Future Work, Summary

## Testing

Run the comprehensive test suite:

```bash
# All tests
pytest backend/tests/test_section_hierarchy.py -v

# Specific test class
pytest backend/tests/test_section_hierarchy.py::TestSectionDetector -v

# With coverage
pytest backend/tests/test_section_hierarchy.py --cov=backend/app/processing/section_detector
```

Test coverage includes:
- Section detection from multiple document types
- Hierarchy construction and navigation
- Numbering pattern detection
- Serialization/deserialization
- Edge cases (empty documents, single sections)

## Example Script

See [example_section_hierarchy.py](../examples/example_section_hierarchy.py) for a complete example that:
1. Ingests a PDF
2. Extracts metadata
3. Detects section hierarchy
4. Displays the hierarchical tree
5. Demonstrates navigation capabilities
6. Saves the hierarchy to JSON

Run it with:

```bash
cd backend
python examples/example_section_hierarchy.py path/to/paper.pdf
```

## Integration Points

### Input from Previous Modules

- **PDF Ingestion Module**: Provides `ValidatedDocument`
- **Document Processing Module**: Provides `ProcessedDocument` with metadata

### Output for Next Modules

- **Section-Aware Chunking**: Uses section boundaries for intelligent splitting
- **Reading Guide Generation**: Uses hierarchy for structured reading paths
- **Targeted Retrieval**: Enables section-filtered search

## Configuration

Customize detection behavior:

```python
pipeline = SectionHierarchyPipeline(
    min_heading_font_size=10.0,    # Minimum font size for headers
    use_docling_structure=True     # Prefer Docling-extracted structure
)
```

## Performance

- **Detection time**: ~0.1-0.5s per document
- **Memory**: Minimal (hierarchy scales linearly with section count)
- **Test coverage**: 87% for detector, 81% for pipeline

## Limitations

- Relies on consistent heading formatting in the document
- May struggle with unconventional numbering schemes
- Performance depends on PDF quality and structure
- Does not normalize section names (removed per requirements)

## Future Enhancements

Potential improvements for future iterations:

1. **Machine Learning-based Detection**: Train a model for more robust header identification
2. **Multi-column Layout Handling**: Better support for complex layouts
3. **Section Content Extraction**: Extract full text for each section
4. **Cross-reference Resolution**: Link section references in text to hierarchy
5. **Table of Contents Extraction**: Parse explicit ToC when available

## API Reference

### SectionHierarchyPipeline

Main entry point for section hierarchy detection.

**Methods**:

- `process_from_processed_document(processed_doc, validated_doc=None) -> SectionDetectionResult`
  - Process a document that already has metadata extracted
  
- `process_from_validated_document(validated_doc) -> SectionDetectionResult`
  - Process a validated document using heuristics
  
- `save_hierarchy(hierarchy, output_path)`
  - Save hierarchy to JSON file
  
- `load_hierarchy(input_path) -> SectionHierarchy`
  - Load hierarchy from JSON file

### SectionHierarchy

Represents the complete section structure.

**Navigation Methods**:

- `get_section(section_id) -> Optional[SectionNode]`
- `get_children(section_id) -> List[SectionNode]`
- `get_parent(section_id) -> Optional[SectionNode]`
- `get_ancestors(section_id) -> List[SectionNode]`
- `get_descendants(section_id) -> List[SectionNode]`
- `get_section_path(section_id) -> List[SectionNode]`

**Query Methods**:

- `find_sections_by_title(title_pattern, case_sensitive=False) -> List[SectionNode]`
- `get_sections_by_level(level) -> List[SectionNode]`

**Serialization**:

- `to_dict() -> Dict`
- `from_dict(data) -> SectionHierarchy`

## Contributing

When extending this module:

1. Add tests for new functionality
2. Maintain backward compatibility
3. Update this README with new features
4. Follow existing code style and patterns
5. Ensure test coverage remains >85%

## Related Documentation

- [Complete Plan](../../plans/1_complete_plan.md) - Module 3 specification
- [Metadata Extraction](../app/processing/README.md) - Upstream module
- [Document Models](../models/document.py) - Core data structures
