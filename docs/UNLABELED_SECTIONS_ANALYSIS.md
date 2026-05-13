# "Unlabeled Section" Chunks: Root Cause & Resolution

## Problem Summary

Your chat endpoint is returning chunks labeled "Unlabeled Section" instead of the actual section names (e.g., "Methods", "Results", etc.). This happens because the document contains text blocks that couldn't be matched to the document's section hierarchy during extraction.

**Example from your query:**
```
Section unknown
The paper describes the following attention methods:
    Vanilla attention
    Low-rank decomposition methods...
    ...
Source Section: Unlabeled Section
```

---

## Root Cause

### Old Behavior (Pre-Fix)

When extracting and chunking PDFs, the system processes text blocks in reading order:

1. **Heading detected** → Map to section in hierarchy
2. **Text block found** → Assign to current section
3. **No current section** (orphaned text) → **Fallback: create "Unlabeled Section" entry** ← **PROBLEM**

**Why this happens:**
- PDF extraction fails to detect some headings (bad OCR, unusual formatting)
- Text blocks appear before any heading is detected (orphaned intro text)
- Section hierarchy is incomplete or malformed

### Where Chunks Get Created

**File:** `backend/rag/retrieval/chunking/section_chunker.py` lines ~920-950

```python
# OLD CODE (pre-fix):
for block in ordered_blocks:
    text = _normalize_text(block.get("text") or "")
    
    if _looks_like_heading_block(block):
        current_section_id = _resolve_section_for_block(...)
        continue
    
    if current_section_id:
        # Assign to section ✓
        buckets[current_section_id].append(text)
    else:
        # No section context → creates "Unlabeled Section" chunks ✗
        unresolved_blocks.append(block)  # Later becomes "Unlabeled Section"
```

---

## The Fix Applied (May 13, 2026)

### Changes to `section_chunker.py`

**New behavior for unresolved blocks:**

```python
# NEW CODE (post-fix):
last_assigned_section_id = None  # Track last successful assignment

for block in ordered_blocks:
    text = _normalize_text(block.get("text") or "")
    
    if _looks_like_heading_block(block):
        resolved_id = _resolve_section_for_block(...)
        if resolved_id:
            current_section_id = resolved_id
            last_assigned_section_id = resolved_id  # ← NEW
        else:
            current_section_id = None
        continue
    
    if current_section_id:
        buckets[current_section_id].append(text)
        last_assigned_section_id = current_section_id
        continue
    
    # Orphaned text block
    if _word_count(text) < 50:
        continue  # Discard extraction artifacts ← NEW
    
    if last_assigned_section_id:
        # Assign to last section instead of "Unlabeled Section" ← NEW
        buckets[last_assigned_section_id].append(text)
        continue
    
    # Only mark as unresolved if truly orphaned
    unresolved_blocks.append(block)
```

**Three improvements:**
1. **Discard small blocks** (<50 tokens) → Likely OCR artifacts
2. **Fall back to last section** → Keep orphaned text with nearest section
3. **Only create "Unlabeled Section" as last resort** → When no previous section exists

### Retrieval-Time Filtering (Added May 13)

**File:** `backend/rag/graph.py` lines ~1825+

```python
def _filter_unlabeled_sections(chunks: list[Any]) -> list[Any]:
    """Filter out Unlabeled sections if they are minority."""
    if not chunks:
        return chunks
    
    unlabeled_hits = [
        chunk for chunk in chunks
        if _result_metadata(chunk).get("section_title") == "Unlabeled Section"
    ]
    
    # Only filter if unlabeled is <50% of results
    if unlabeled_hits and len(unlabeled_hits) <= len(chunks) / 2:
        return [
            chunk for chunk in chunks
            if _result_metadata(chunk).get("section_title") != "Unlabeled Section"
        ]
    return chunks

# Applied in retrieve-and-QA path:
deduped_hits = _dedupe_near_identical_chunks(filtered_hits)
deduped_hits = _filter_unlabeled_sections(deduped_hits)  # ← NEW
top_hits = deduped_hits[:QA_TOP_K]
```

---

## Why You Still See "Unlabeled Section"

### Scenario 1: Existing Chunks in Index (Most Likely)

Your Qdrant index contains chunks indexed **before May 13, 2026** with `section_title="Unlabeled Section"`.

**These won't automatically disappear because:**
- The fix applies to NEW chunks created during extraction
- Existing indexed chunks remain unchanged
- Index rebuild required to apply fix retroactively

### Scenario 2: Chat Path Not Filtering

The chat endpoint uses `backend/qa_bot/retriever.py` which calls `_retrieve_for_question()`. This function now has the adaptive threshold and unlabeled filtering, but **only for the retrieve-and-QA path** (guide questions).

**To apply to chat path too**, check if the filter is being called in the chat retrieval code path.

---

## Solution

### Option 1: Clean Up Existing Index (Recommended)

Run the cleanup script when Qdrant is running:

```bash
cd /home/aman/storage/Python/Projects/Research\ Paper\ Assistant
source env_research/bin/activate
python cleanup_unlabeled_sections.py
```

This will:
1. Show you how many "Unlabeled Section" chunks exist
2. Display section distribution (which section has most chunks)
3. Optionally delete all "Unlabeled Section" chunks
4. Guide you to re-index documents with the new code

### Option 2: Re-Index All Documents

After cleaning up, re-extract and re-index all papers via the UI:

1. Delete papers from the system
2. Re-upload PDFs
3. New chunks will use the improved section assignment logic
4. No more "Unlabeled Section" entries

### Option 3: Live with Filter (Short Term)

The retrieval-time filter already removes "Unlabeled Section" chunks when they're a minority. If this is working in your chat, the fix is partially active.

**To verify filtering is working:**
- Check `backend/rag/graph.py` line ~1825
- Search for `_filter_unlabeled_sections` being called in the chat retrieval path
- If not found, add it after deduplication step

---

## Files Changed (May 13, 2026)

| File | Change | Impact |
|------|--------|--------|
| `backend/rag/retrieval/chunking/section_chunker.py` | Discard <50-token blocks; fallback to last section | Prevents new "Unlabeled Section" chunks |
| `backend/rag/graph.py` | Added `_filter_unlabeled_sections()` + `_adaptive_threshold()` | Filters out unlabeled chunks from retrieval results |
| `backend/config.py` | Increased `SCOPED_TOP_K` (8→15), `FALLBACK_TOP_K` (4→8), `QA_TOP_K` (4→6) | Better chunk coverage |
| `backend/qa_bot/nodes.py` | Returns `retrieved_chunks` metadata | Exposes section_title in chat response |
| `backend/api/app.py` | Added `sources` array with section_title, page, preview | User sees which section each chunk came from |

---

## Next Steps

1. **Start Qdrant service** if not running
2. **Run cleanup script:**
   ```bash
   python cleanup_unlabeled_sections.py
   ```
3. **Review diagnostic output** to see:
   - How many "Unlabeled Section" chunks exist
   - Which sections have most chunks
   - Whether filter is working
4. **Optionally delete** old "Unlabeled Section" chunks
5. **Re-index documents** with updated code to ensure no new unlabeled chunks

---

## Verification

To confirm the fix is working for NEW documents:

1. Upload a test PDF after fix deployment
2. Query for content from that document
3. Verify all chunks have actual section names (no "Unlabeled Section")
4. Check API response includes `"scoped": true/false` and proper `sources` array

---

## Questions?

**How to diagnose further:**
- Check if the issue persists after re-indexing
- Monitor Qdrant chunk distribution before/after cleanup
- Verify section hierarchy extraction is working correctly
