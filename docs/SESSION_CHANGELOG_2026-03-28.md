# Session Changelog - 2026-03-28

## Scope
Fixed incorrect section assignment in chunking when multiple headings appear on the same page.

## Changes Made

### 1. Replaced coarse page-based section assignment with nearest-heading assignment
- File changed: `backend/rag/retrieval/chunking/section_chunker.py`
- Added nearest-preceding-heading logic over `extracted_elements.text_blocks` in reading order:
  1. Iterate blocks in reading order.
  2. Update `current_section` when a valid heading block is encountered.
  3. Assign each non-heading block to the current section.
- This prevents same-page heading collisions from assigning body text to the wrong section.

### 2. Added heading-quality filter to avoid false heading matches
- Heading candidates are now rejected when:
  - They have more than 12 words, or
  - They have neither numbering prefix (`^\d+[\.\d]*\s`) nor title-case structure.
- This reduces bold/body-text misclassification as section headings.

### 3. Preserved fallback chain for robust section assignment
- Fallback order in chunk text mapping is now:
  1. Nearest valid preceding heading (primary)
  2. Docling element-level section tags (`section_title` / `section`) for unresolved blocks
  3. Existing page-based mapping for remaining gaps
  4. Existing fulltext segmentation fallback when page text is unavailable

### 4. Added warning-only post-chunk validation pass
- After chunk generation, a validation pass compares assigned chunk `section_title` against nearest-heading expectation.
- Mismatches are logged with `logger.warning(...)`.
- No exceptions are raised and pipeline execution continues.

### 5. Metadata contract preserved
- Chunk metadata fields are unchanged:
  - `section_id`
  - `section_title`
  - `section_path`
  - `section_path_ids`

## Not Changed
- No changes to Qdrant write/upsert path.
- No changes to retrieval filters.
- No changes to `backend/extraction/app/section_detector.py` or `backend/extraction/app/metadata_extractor.py` in this fix.

## Validation
- Python diagnostics for `section_chunker.py`: no errors.
- Compile check: `python3 -m py_compile backend/rag/retrieval/chunking/section_chunker.py` succeeded.
