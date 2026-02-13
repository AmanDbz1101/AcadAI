# Section Hierarchy Detection - Quick Start Guide

## Installation

The module is already integrated into the backend. No additional installation needed.

## Quick Example

```python
from backend.pipelines import (
    IngestPipeline,
    MetadataExtractionPipeline, 
    SectionHierarchyPipeline
)
from pathlib import Path

# Initialize pipelines
ingest = IngestPipeline()
metadata = MetadataExtractionPipeline()
hierarchy_pipeline = SectionHierarchyPipeline()

# Process a PDF
pdf_path = Path("path/to/paper.pdf")

# Step 1: Ingest
validated_doc = ingest.ingest(pdf_path)

# Step 2: Extract metadata
processed_doc = metadata.process(validated_doc)

# Step 3: Detect section hierarchy
result = hierarchy_pipeline.process_from_processed_document(processed_doc)
hierarchy = result.hierarchy

# Use the hierarchy
print(f"Total sections: {hierarchy.total_sections}")
print(f"Max depth: {hierarchy.max_depth}")
print(f"Confidence: {hierarchy.confidence_score:.2f}")

# Get top-level sections
for section in hierarchy.get_sections_by_level(1):
    print(f"- {section.title} (Page {section.page_start})")
```

## Run the Example Script

```bash
cd backend
source ../env_research/bin/activate
python examples/example_section_hierarchy.py path/to/paper.pdf
```

## Run Tests

```bash
cd /home/aman/storage/Python/Projects/Research\ Paper\ Assistant
source env_research/bin/activate
python -m pytest backend/tests/test_section_hierarchy.py -v
```

## Common Use Cases

### 1. Navigate Section Tree

```python
# Get a specific section
section = hierarchy.find_sections_by_title("Introduction")[0]

# Get its children
children = hierarchy.get_children(section.section_id)

# Get its parent
parent = hierarchy.get_parent(section.section_id)

# Get all ancestors
ancestors = hierarchy.get_ancestors(section.section_id)

# Get full path from root
path = hierarchy.get_section_path(section.section_id)
```

### 2. Search for Sections

```python
# Find sections by title pattern
method_sections = hierarchy.find_sections_by_title("method", case_sensitive=False)

# Get all sections at a specific level
level1 = hierarchy.get_sections_by_level(1)
level2 = hierarchy.get_sections_by_level(2)
```

### 3. Save and Load

```python
from pathlib import Path

# Save hierarchy
output_path = Path("output/hierarchy.json")
hierarchy_pipeline.save_hierarchy(hierarchy, output_path)

# Load hierarchy
loaded = hierarchy_pipeline.load_hierarchy(output_path)
```

## Next Steps

1. ✅ Section Hierarchy Detection is complete
2. ⏭️ Ready for Module 4: Section-Aware Chunking
3. The hierarchy will be used to create intelligent text chunks with section metadata

## Documentation

- **Full README**: [SECTION_HIERARCHY_README.md](SECTION_HIERARCHY_README.md)
- **Implementation Summary**: [SECTION_HIERARCHY_IMPLEMENTATION_SUMMARY.md](../SECTION_HIERARCHY_IMPLEMENTATION_SUMMARY.md)
- **Complete Plan**: [1_complete_plan.md](../plans/1_complete_plan.md) (Module 3)

## Troubleshooting

### Import Errors

If you get import errors, make sure you're in the project root and the virtual environment is activated:

```bash
cd /home/aman/storage/Python/Projects/Research\ Paper\ Assistant
source env_research/bin/activate
```

### Test Failures

Run tests with verbose output to see details:

```bash
python -m pytest backend/tests/test_section_hierarchy.py -v --tb=short
```

## API Quick Reference

### SectionHierarchyPipeline

```python
# Main methods
result = pipeline.process_from_processed_document(processed_doc)
result = pipeline.process_from_validated_document(validated_doc)
pipeline.save_hierarchy(hierarchy, output_path)
hierarchy = pipeline.load_hierarchy(input_path)
```

### SectionHierarchy

```python
# Navigation
section = hierarchy.get_section(section_id)
children = hierarchy.get_children(section_id)
parent = hierarchy.get_parent(section_id)
ancestors = hierarchy.get_ancestors(section_id)
descendants = hierarchy.get_descendants(section_id)
path = hierarchy.get_section_path(section_id)

# Search
sections = hierarchy.find_sections_by_title(pattern, case_sensitive=False)
sections = hierarchy.get_sections_by_level(level)

# Serialization
data = hierarchy.to_dict()
hierarchy = SectionHierarchy.from_dict(data)
```

### SectionNode

```python
# Properties
section.section_id       # Unique ID
section.title           # Clean title (no numbering)
section.numbering       # Section number (e.g., "1.2.3")
section.level           # Depth (1-6)
section.page_start      # Starting page
section.page_end        # Ending page
section.parent_id       # Parent section ID
section.child_section_ids  # List of children IDs
section.full_path       # Formatted path with numbering
```
