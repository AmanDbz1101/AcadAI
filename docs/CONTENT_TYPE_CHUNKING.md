# Content-Type-Aware Chunking Implementation

## Overview

Enhanced the document chunking pipeline to preserve and distinguish different content types (text, tables, figures) when processing research PDFs. This prevents tables and figure captions from being fragmented into regular text chunks, improving retrieval quality.

## Changes Made

### 1. Chunk Model (`backend/rag/retrieval/chunking/models.py`)

Added a new `content_type` field to the `Chunk` model:

```python
content_type: str = Field(
    default="text",
    description="Content type ('text', 'table', or 'figure')",
)
```

**Valid values:**
- `"text"` — Regular body text (default)
- `"table"` — Markdown-formatted tables
- `"figure"` — Figure captions + image references

**Payload serialization:** The `content_type` field is included in `to_payload()` for downstream access by the indexer and retriever.

### 2. Section Chunker (`backend/rag/retrieval/chunking/section_chunker.py`)

#### A. Element Extraction

Added `_load_extracted_elements()` to load table/figure metadata from `_complete.json`:

```python
@staticmethod
def _load_extracted_elements(document_id, output_dir) -> Optional[ElementDict]:
    """Load extracted_elements dict from _complete.json."""
```

**Source:** Docling's `extracted_elements` object containing:
- `tables[]` — Each with `id`, `page`, `label`, `markdown` (or `text`), `label`
- `figures[]` — Each with `id`, `page`, `caption`, `image_path`, `label`

#### B. Section-scoped Element Extraction

Added `_extract_elements_for_section()` to filter tables/figures by page range:

```python
@staticmethod
def _extract_elements_for_section(
    elements, page_start, page_end
) -> tuple[list[dict], list[dict]]:
    """Extract tables and figures within [page_start, page_end]."""
```

Only elements within the section's page boundaries are included.

#### C. Table Chunking

New method `_create_table_chunk()` creates one chunk per table:

- **Content:** Uses `table["markdown"]` (preferred) or `table["text"]`
- **No splitting:** Entire table is kept as one chunk
- **Chunk level:** Always `"coarse"` (treated as significant structural unit)
- **content_type:** `"table"`
- **element_ids:** References the table's Docling ID

**Example output:**
```markdown
| Layer Type          | Complexity   | Sequential Ops | Max Path |
|---------------------|--------------|----------------|----------|
| Self-Attention      | O(n²·d)      | O(1)           | O(1)     |
| Recurrent           | O(n·d²)      | O(n)           | O(n)     |
```

#### D. Figure Chunking

New method `_create_figure_chunk()` creates one chunk per figure:

- **Content:** `caption + "\n[Image: image_path]"` or caption-only if path missing
- **No splitting:** Caption (and reference) stay intact
- **Chunk level:** Always `"coarse"`
- **content_type:** `"figure"`
- **element_ids:** References the figure's Docling ID

**Example output:**
```
Figure 1: Multi-Head Attention mechanism visualized across three parallel heads.
[Image: figures/multi-head-attention.png]
```

#### E. Updated Processing Flow

In `chunk_document()`, the new processing order is:

1. **Load extracted elements** from `_complete.json`
2. **For each section:**
   - Extract tables/figures in this section's page range
   - **Create table chunks** (high fidelity, no fragmentation)
   - **Create figure chunks** (preserves captions)
   - **Create text chunks** from remaining body text (existing logic)

**Chunk index continuity:** All chunks (text, table, figure) share a single monotonic `chunk_index` counter, ensuring deterministic ordering.

### 3. Fallback Fallback Path

Updated `_fallback_full_text_chunks()` to mark chunks as `content_type="text"` when section hierarchy is unavailable.

## Metadata Structure

Every chunk now carries:

```python
{
    "chunk_id": "uuid",
    "document_id": "uuid",
    "content": "...",
    "content_type": "text|table|figure",  # NEW
    "token_count": 0,
    "chunk_index": 42,
    "chunk_level": "fine|coarse",
    "section_id": "sec_3_2",
    "section_title": "Attention Mechanisms",
    "section_path": ["Model Architecture", "Attention", "Attention Mechanisms"],
    "page_start": 5,
    "page_end": 7,
    "element_ids": ["docling_elem_id_123"],
    "source_file": "document.pdf",
}
```

## Retrieval Benefits

### Before
- Tables split into fragments: `"...| Layer A | Complexity |..."`, `"...| Recurrent | O(n·d²) |..."` → noisy hits
- Captions detached from figures and mixed with body text
- No way to filter/prioritize structured content

### After
- **Whole tables retrieved together** → better context preservation
- **Captions stay with figures** → coherent figure-text pairs
- **Can filter by content_type** in retrieval → option to bias toward tables/figures for structured queries
- **Cleaner embeddings** → higher recall for table/figure queries

## Files Modified

- `backend/rag/retrieval/chunking/models.py` — Added `content_type` field
- `backend/rag/retrieval/chunking/section_chunker.py` — Enhanced element extraction & chunking logic

## Files NOT Modified (as requested)

- `backend/rag/retrieval/indexer.py`
- `backend/rag/retrieval/hybrid_retriever.py`
- `backend/rag/qdrant_store.py`
- `backend/rag/extractors/graph.py`

These modules can optionally leverage `content_type` via the payload, but no changes were required.

## Migration Notes

- **Backward compatible:** Existing chunks default to `content_type="text"`
- **Database:** If re-indexing, vectors will have the new metadata field
- **Queries:** Retrievers can optionally filter by content_type; existing queries work unchanged

## Testing Recommendations

1. Verify table markdown is extracted completely (no truncation)
2. Confirm figures with missing captions gracefully use `"[Figure without caption]"`
3. Check chunk ordering remains deterministic across re-runs
4. Validate section path breadcrumbs are accurate for tables/figures
5. Test fallback path when `_complete.json` is unavailable
