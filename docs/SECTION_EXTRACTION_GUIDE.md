# Section Content Extraction Guide

## Overview

Your research paper backend system **already has the infrastructure to extract and query specific sections** like Introduction, Conclusion, Methods, Results, etc. from papers.

The database stores:
- **27-28 sections per paper** with hierarchy (title, level, page numbers)
- **274+ text blocks** directly linked to sections via `section_id`
- Full content for each section

## Quick Start

### Option 1: Using the Section Query Module (Recommended)

```python
from backend.rag.retrieval.section_query import (
    get_introduction,
    get_conclusion,
    get_all_sections,
    get_all_documents
)

# Get all papers in database
documents = get_all_documents()
#  Returns: [{'id': 'uuid', 'filename': 'paper.pdf', 'title': '...', 'total_sections': 27}, ...]

# Get introduction from a specific paper
doc_id = documents[0]['id']
intro = get_introduction(doc_id)

print(f"Title: {intro['title']}")
print(f"Pages: {intro['page_start']}-{intro['page_end']}")
print(f"Content length: {intro['content_length']} characters")
print(f"Content preview: {intro['content'][:500]}")

# Get conclusion
conclusion = get_conclusion(doc_id)

# Get multiple sections at once
sections = get_all_sections(doc_id)
for name, section in sections.items():
    if section['found']:
        print(f"✓ {name}: {section['content_length']} chars, pages {section['page_start']}")
    else:
        print(f"✗ {name}: Not found")

# Custom section extraction
custom_sections = get_all_sections(
    doc_id,
    keywords={
        'introduction': ['introduction', 'intro', 'background'],
        'methodology': ['method', 'methodology', 'approach'],
        'findings': ['result', 'finding', 'analysis'],
        'summary': ['conclusion', 'summary', 'discussion'],
    }
)
```

### Option 2: Raw SQL Queries

If you prefer direct database access:

```python
from sqlalchemy import create_engine, text
import os

# Setup connection
database_url = os.getenv("DATABASE_URL") or "postgresql+psycopg://postgres@localhost:5432/research_agent"
engine = create_engine(database_url)

with engine.connect() as conn:
    # Find introduction section
    result = conn.execute(text("""
        SELECT id, title, page_start, page_end
        FROM sections
        WHERE document_id = :doc_id
          AND title ILIKE '%introduction%'
        LIMIT 1
    """), {'doc_id': 'your-uuid-here'})
    
    section = result.first()
    if section:
        section_id, title, page_start, page_end = section
        
        # Get all text content for this section
        content_result = conn.execute(text("""
            SELECT content FROM text_blocks
            WHERE section_id = :sec_id
            ORDER BY reading_order
        """), {'sec_id': section_id})
        
        full_text = "\n\n".join(row[0] for row in content_result if row[0])
        print(full_text)
```

### Option 3: Using the Test File

Run the comprehensive test to see all sections:

```bash
cd /home/aman/storage/Python/Projects/Research\ Paper\ Assistant
python backend/tests/test_extract_sections_working.py
```

Output shows:
- All documents in the database
- All section locations and metadata
- Full introduction and conclusion content

## Database Schema Reference

### documents table
```
id (UUID) | filename | title | total_sections | extraction_method | created_at
```

### sections table
```
id (VARCHAR)          -- Section ID key
document_id (UUID)    -- References documents.id
title (TEXT)          -- Section heading
level (INTEGER)       -- 1=top-level, 2=subsection, etc.
numbering (VARCHAR)   -- Section number (e.g., "2.1", "IV-B")
parent_id (VARCHAR)   -- Parent section ID for hierarchy
page_start (INTEGER)  -- Starting page number
page_end (INTEGER)    -- Ending page number
reading_order (INT)   -- Position in document
```

### text_blocks table
```
id (VARCHAR)        -- Unique text block ID
document_id (UUID)  -- References documents.id
section_id (VARCHAR) -- References sections.id
content (TEXT)      -- Actual text content
section_title (TEXT) -- Denormalized section title
section_level (INT)  -- Denormalized section level
section_path (TEXT)  -- Full hierarchical path
reading_order (INT)  -- Position in section
page_number (INT)    -- Page this block appears on
label (VARCHAR)      -- Content type (e.g., "title", "body")
```

## Example Queries

### Find all top-level sections in a paper
```python
from backend.rag.retrieval.section_query import get_all_sections

sections = get_all_sections(doc_id)
top_level = {name: sec for name, sec in sections.items() if sec['found'] and sec['level'] == 1}
for name, sec in top_level.items():
    print(f"{sec['numbering']} {sec['title']}")
```

### Search for keyword in a section
```python
from backend.rag.retrieval.section_query import get_conclusion

conclusion = get_conclusion(doc_id)
if "future work" in conclusion['content'].lower():
    print("This paper mentions future work in conclusion")
```

### Compare sections across multiple papers
```python
from backend.rag.retrieval.section_query import get_introduction, get_all_documents

docs = get_all_documents()
intros = {}

for doc in docs:
    intro = get_introduction(doc['id'])
    if intro['found']:
        intros[doc['filename']] = intro['content_length']

for filename, length in sorted(intros.items(), key=lambda x: x[1]):
    print(f"{filename}: {length} chars")
```

## Current Sample Data

### Papers in Database
1. **attention.pdf** - "Attention is All You Need" (Transformer paper)
   - 27 sections
   - 274 text blocks
   - Introduction: page 3 (1911 chars)
   - Conclusion: page 11 (1221 chars)

2. **Gated Attention.pdf**
   - 28 sections
   - Related extraction data

## Integration with RAG Pipeline

The section extraction system integrates with your RAG retrieval pipeline:

```python
from backend.rag.retrieval.pipeline import RetrievalPipeline
from backend.rag.retrieval.section_query import get_introduction

# Get introduction  
intro = get_introduction(doc_id)
intro_text = intro['content']

# Use with RAG pipeline
pipeline = RetrievalPipeline()
results = pipeline.query(
    query="What is the main contribution?",
    document_id=doc_id,
)

# Or query only within a section using the hybrid retriever
from backend.rag.retrieval.search.hybrid_retriever import HybridRetriever
results = retriever.retrieve(
    query="methodology",
    document_id=doc_id,
    section_title_contains="method"  # Filter by section
)
```

## Adding New Papers

When you add papers to the system:

1. The extraction pipeline automatically detects sections
2. Sections are stored in the `sections` table
3. Text content is split into blocks and linked via `section_id`
4. You can immediately query them using the tools above

## Performance Notes

- Section queries are fast (direct section_id index)
- Default indexes on `document_id` and `section_id`
- Recommend caching section lists for frequently accessed papers
- Text blocks are ordered by `reading_order` for proper rebuild

## Troubleshooting

**Section not found?**
- Check spelling of section title
- Try different keywords (paper might use "Methods" vs "Methodology")
- Use `get_all_sections()` without a keywords filter to see what's available

**Empty content?**
- Check `text_blocks` has rows with matching `section_id`
- Verify extraction completed successfully (check extraction_method in documents table)
- Some sections might have mostly images/tables (low text content)

**Database connection fails?**
- Ensure `DATABASE_URL` environment variable is set
- Or PostgreSQL is running at localhost:5432
- Check credentials in .env file

## Next Steps for Enhancement

If you want to improve the system further:

1. **Add section-aware embeddings** to Qdrant vectors (already partially done with `section_title`, `section_path` metadata)

2. **Create section-scoped search** - retrieve only within introduction, methods, conclusion, etc.

3. **Build section hierarchy visualization** - show nesting structure

4. **Add section completion tracking** - monitor if all expected sections were extracted

5. **Implement section templates** - define expected sections for different paper types

6. **Add cross-reference finding** - show which sections reference which other sections

## Files

- **Query Interface**: [`backend/rag/retrieval/section_query.py`](backend/rag/retrieval/section_query.py)
- **Working Test**: [`backend/tests/test_extract_sections_working.py`](backend/tests/test_extract_sections_working.py)
- **Schema Inspection**: [`backend/tests/test_schema_inspection.py`](backend/tests/test_schema_inspection.py)

## Support

For issues or questions about section extraction:
1. Check the test output: `python backend/tests/test_extract_sections_working.py`
2. Inspect database schema: `python backend/tests/test_schema_inspection.py`
3. Review the section_query module source code for all available functions
