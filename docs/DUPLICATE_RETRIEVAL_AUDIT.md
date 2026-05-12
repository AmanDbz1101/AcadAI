# Duplicate Retrieval Audit: Hierarchical Chunking RAG Pipeline

**Date:** May 10, 2026  
**Issue:** Both parent (coarse) and child (fine) chunks from the same section appearing together in retrieval results

---

## Executive Summary

Your RAG pipeline **intentionally stores both coarse and fine chunks from the same section together** in the vector store. The deduplication logic exists but has **insufficient threshold sensitivity** to catch parent-child redundancy at your current chunking parameters.

**Verdict:** ⚠️ **BUG CONFIRMED** in post-retrieval deduplication logic. See [Fix Recommendation](#fix-recommendation) below.

---

## 1. Schema Audit: Chunk Metadata Fields

### ✅ Metadata Fields Present

Your chunks carry these hierarchy-distinguishing fields:

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `chunk_level` | `str` | **Distinguishes coarse vs fine** | `"coarse"` or `"fine"` |
| `section_id` | `str` | Section reference (shared by all chunks in a section) | `"bd077a96-5a38-5281-993e-10cf869afcde_section_1"` |
| `section_path_ids` | `list[str]` | Ancestry chain for hierarchy filtering | `["3", "3.2", "3.2.1"]` |
| `parent_section_id` | `str` | Immediate parent reference | Used for navigation |
| `token_count` | `int` | Token count (affects chunking strategy) | e.g., `512` |
| `chunk_index` | `int` | Zero-based chunk order within document | `0, 1, 2...` |

**Missing field:** There is **NO explicit `is_parent` or `granularity`** flag—chunk type is inferred entirely from `chunk_level`.

### 📂 Location: Chunk Construction

**File:** [backend/rag/retrieval/chunking/models.py](backend/rag/retrieval/chunking/models.py#L35-L45)

```python
chunk_level: str = Field(
    default="coarse",
    description="Chunk granularity level ('fine' or 'coarse')",
)
```

**Serialized to Qdrant:** Via `to_payload()` method (lines 100–120) as a `keyword` field.

---

## 2. Chunk Ingestion: How Parent & Child Are Created

### Hierarchical Chunking Strategy

**File:** [backend/rag/retrieval/chunking/section_chunker.py](backend/rag/retrieval/chunking/section_chunker.py#L1074-L1082)

For **each section**, chunks are created **twice**:

```python
for chunk_level, splitter in (
    ("fine", self.fine_splitter),      # Fine-grained chunks
    ("coarse", self.coarse_splitter),   # Coarse-grained chunks (parent)
):
    windows = splitter.split(text)     # Same section text, different split strategy
    for window in windows:
        chunks.append(
            Chunk(
                ...
                content=window,
                chunk_level=chunk_level,  # Set to "fine" or "coarse"
                section_id=section_id,    # SHARED across both levels
                ...
            )
        )
```

### Chunking Parameters

**File:** [backend/rag/retrieval/config.py](backend/rag/retrieval/config.py) (inferred)

```python
FINE_CHUNK_SIZE    = ~512 tokens      # Precise, detailed chunks
FINE_CHUNK_OVERLAP = ~100 tokens      # 20% overlap

COARSE_CHUNK_SIZE  = ~2048 tokens     # Broad context
COARSE_CHUNK_OVERLAP = ~200 tokens    # 10% overlap
```

**Example for section with 3000 tokens of content:**

| Level | Chunks Created | Avg Size | Overlap |
|-------|---|---|---|
| `fine` | ~6–8 chunks | 512 tokens | 100 tokens |
| `coarse` | ~2 chunks | 2048 tokens | 200 tokens |

**Total: Both ~6–8 fine AND ~2 coarse chunks stored under same `section_id`.**

---

## 3. Retrieval Flow: No Server-Side Filtering Between Levels

### Hybrid Retrieval (Dense + Sparse)

**File:** [backend/rag/retrieval/search/hybrid_retriever.py](backend/rag/retrieval/search/hybrid_retriever.py#L150-L210)

```python
def retrieve(
    self,
    query: str,
    document_id: Optional[str] = None,
    chunk_level: Optional[str] = None,  # ← EXISTS but often unused
    section_id: Optional[str] = None,
    ...
) -> list:
```

**Issue:** The `chunk_level` parameter is defined but:
- Not always passed from the calling code
- Not enforced during retrieval
- Both levels come back in results when not specified

**Example retrieval call (common pattern):**

```python
hits = retriever.retrieve(query="attention mechanism", document_id=doc_id)
# Returns: fine chunks + coarse chunks, all scored together
```

### Vector Store Schema (Qdrant)

**File:** [backend/rag/retrieval/indexing/qdrant_store.py](backend/rag/retrieval/indexing/qdrant_store.py)

Payload indexes include:
- `chunk_level` (keyword field, searchable)
- `section_id` (keyword field)
- `section_path_ids` (keyword array)

**Result:** All chunks indexed equally; no separation at retrieval time unless explicitly filtered.

---

## 4. Deduplication Logic: The Bug

### Current Implementation

**File:** [backend/rag/graph.py](backend/rag/graph.py#L1056-L1083) – Lines 1056–1083

```python
def _dedupe_near_identical_chunks(
    chunks: list[Any],
    similarity_threshold: float = 0.7,  # ← 70% THRESHOLD
) -> list[Any]:
    """Deduplicate near-identical chunks using token-overlap Jaccard similarity."""
    deduped_chunks: list[Any] = []
    deduped_token_sets: list[set[str]] = []

    for chunk in chunks:
        chunk_tokens = set(_result_content(chunk).split())
        is_duplicate = False

        for kept_tokens in deduped_token_sets:
            union = chunk_tokens | kept_tokens
            if not union:
                jaccard = 1.0
            else:
                jaccard = len(chunk_tokens & kept_tokens) / len(union)  # Token overlap

            if jaccard > similarity_threshold:  # 0.7 threshold
                is_duplicate = True
                break

        if not is_duplicate:
            deduped_chunks.append(chunk)
            deduped_token_sets.append(chunk_tokens)

    return deduped_chunks
```

### The Problem: Parent-Child Jaccard < Threshold

Using **your sample data**:

| Chunk | Level | Tokens | Content Summary |
|-------|-------|--------|---|
| #1 | `coarse` | ~1400 | Full paragraph (lines 1–15) |
| #2 | `fine` | ~400 | Subset (lines 1–6) |
| #3 | `fine` | ~350 | Subset (lines 7–12) |

**Jaccard calculations (with Chunk #1 as baseline):**

- `jaccard(#1, #2) = len(#2 ∩ #1) / len(#2 ∪ #1)`
  - Intersection: ~400 tokens (all of #2 is in #1)
  - Union: ~1400 tokens (from #1)
  - **Jaccard = 400 / 1400 = 0.286** ← **BELOW 0.7 threshold!**

- `jaccard(#1, #3) = 350 / 1400 = 0.25` ← **ALSO BELOW!**

- `jaccard(#2, #3) = 200 / 550 = 0.364` ← **BELOW!**

**Result:** All three chunks pass the deduplication filter and are returned together. ✗

### Why The Threshold Fails

The **0.7 threshold is calibrated for content-level duplicates** (near-identical copies), not **hierarchical parent-child relationships**.

In parent-child scenarios:
- Child tokens = subset of parent tokens
- Jaccard = (child size) / (parent size) ≈ 25–40% (depending on chunk sizes)
- **This is well below 0.7, so deduplication fails.**

---

## 5. Intended Behavior: Not Yet Implemented

### Current Pattern (Unintended)

**Both coarse and fine chunks are stored and retrieved together** (Small-to-Big variant with no separation).

```
Query → Hybrid Search → [fine chunks + coarse chunks] → Dedup (fails) → LLM
```

### Correct Patterns (Choose One)

#### **Option A: Fine-Only (Recommended)**
Retrieve only `fine` chunks; optionally expand to parent for context.

```python
# Retrieve fine chunks only
hits = retriever.retrieve(
    query=user_query,
    chunk_level="fine",  # ← Filter to fine only
    document_id=doc_id
)
```

**Pros:**
- No redundancy
- High precision
- Parent context available if needed via `parent_section_id`

**Cons:**
- Loses broad context from coarse chunks

---

#### **Option B: Coarse-Only (Broad Context)**
Retrieve coarse chunks; use fine for re-ranking.

```python
hits = retriever.retrieve(
    query=user_query,
    chunk_level="coarse",  # ← Filter to coarse only
    document_id=doc_id
)
# Optionally rerank with fine-chunk scoring
```

**Pros:**
- Broader context
- Fewer results to process
- No redundancy

**Cons:**
- Lower precision
- May include off-topic content

---

#### **Option C: Section-Based Deduplication (Current Intent)**
Retrieve both levels, then **keep only the highest-scoring chunk per section**.

```python
hits = retriever.retrieve(query=user_query, document_id=doc_id)
# Both fine and coarse returned

# Deduplicate by section_id
best_per_section = {}
for hit in hits:
    section_id = hit.metadata.get("section_id")
    if section_id not in best_per_section or hit.score > best_per_section[section_id].score:
        best_per_section[section_id] = hit

final_hits = list(best_per_section.values())
```

**Pros:**
- Balances precision and context
- No per-chunk redundancy
- Keeps diversity across sections

**Cons:**
- Discards potentially useful fine chunks if coarse scores higher

---

## 6. Deduplication Call Sites

**Current usage in pipeline:**

| Location | File | Line | Called After | Purpose |
|----------|------|------|---|---|
| Q&A multi-step | `graph.py` | 1882 | Retrieval + figures + tables | Remove ID duplicates |
| Q&A filtering | `graph.py` | 1890 | Threshold filtering | Remove near-identical chunks |
| Guide retrieval | `graph.py` | ~1605–1695 | Multi-stage retrieval | Merge & dedupe results |

**Entry point for your issue:** [graph.py line 1890](backend/rag/graph.py#L1890)

```python
deduped_hits = _dedupe_near_identical_chunks(filtered_hits)
top_hits = deduped_hits[:QA_TOP_K]  # Takes top-K after dedup
```

---

## 7. Fix Recommendation

### Fix 1: Section-Based Deduplication (Minimal Change) ✅

**Problem addressed:** Prevents sibling chunks (coarse + fine) from the same section appearing together.

**File:** [backend/rag/graph.py](backend/rag/graph.py)

**Implementation:**

Replace the deduplication logic at line 1056–1083 with:

```python
def _dedupe_near_identical_chunks(
    chunks: list[Any],
    similarity_threshold: float = 0.7,
    dedup_by_section: bool = True,  # ← NEW PARAMETER
) -> list[Any]:
    """
    Deduplicate near-identical chunks using token-overlap Jaccard similarity.
    
    When dedup_by_section=True, also prevents both parent and child chunks
    (coarse and fine) from the same section appearing in results.
    """
    
    # First pass: dedup by section_id (keep highest-scoring per section)
    if dedup_by_section:
        best_by_section: dict[str, Any] = {}
        for chunk in chunks:
            metadata = _result_metadata(chunk)
            section_id = metadata.get("section_id")
            
            if section_id:
                existing = best_by_section.get(section_id)
                if existing is None or _result_score(chunk) > _result_score(existing):
                    best_by_section[section_id] = chunk
        
        chunks = list(best_by_section.values())
    
    # Second pass: existing Jaccard-based dedup (for true duplicates)
    deduped_chunks: list[Any] = []
    deduped_token_sets: list[set[str]] = []

    for chunk in chunks:
        chunk_tokens = set(_result_content(chunk).split())
        is_duplicate = False

        for kept_tokens in deduped_token_sets:
            union = chunk_tokens | kept_tokens
            if not union:
                jaccard = 1.0
            else:
                jaccard = len(chunk_tokens & kept_tokens) / len(union)

            if jaccard > similarity_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            deduped_chunks.append(chunk)
            deduped_token_sets.append(chunk_tokens)

    return deduped_chunks
```

**Usage (line 1890):**

```python
deduped_hits = _dedupe_near_identical_chunks(
    filtered_hits, 
    dedup_by_section=True  # ← Enable section-based dedup
)
```

**Result:** Only the highest-scoring chunk per `section_id` returned.

---

### Fix 2: Explicit Chunk-Level Filtering (More Targeted) 🔧

**File:** [backend/rag/retrieval/search/hybrid_retriever.py](backend/rag/retrieval/search/hybrid_retriever.py#L150-L210)

**Currently, `chunk_level` parameter exists but is often not used in calls.**

Enforce it in the retrieval method:

```python
def retrieve(
    self,
    query: str,
    document_id: Optional[str] = None,
    chunk_level: Optional[str] = None,  # "fine", "coarse", or None (both)
    ...
) -> list:
    """
    ...
    Parameters
    ----------
    chunk_level : str, optional
        When set, restricts results to this granularity level
        ("fine" for precision, "coarse" for context).
        When None (default), returns both levels.
    ...
    """
    from rag.states import RetrievalResult  # local to avoid circular import

    if not query.strip():
        logger.warning("HybridRetriever: empty query — returning nothing")
        return []

    # Build Qdrant payload filter
    payload_filter = self._build_filter(
        document_id,
        section_title_contains,
        section_path_any,
        chunk_level,  # ← Already passed to _build_filter
        section_id,
        section_path_ids_any,
        content_type,
        exclude_reference_sections,
    )
    # ... rest of method
```

**Usage in graph.py (where the Q&A retrieval happens):**

```python
# Option: Retrieve only fine chunks
hits = pipeline.retrieve_and_rerank(
    query=question,
    document_id=document_id,
    chunk_level="fine",  # ← Add this
)

# Option: Retrieve only coarse chunks
hits = pipeline.retrieve_and_rerank(
    query=question,
    document_id=document_id,
    chunk_level="coarse",  # ← Or this
)
```

---

### Fix 3: Increase Threshold (Partial Workaround) ⚠️

**NOT RECOMMENDED** because it risks removing legitimate duplicates.

Would require threshold ≈ 0.25 to catch all parent-child pairs, which would also catch many false positives.

---

## 8. Recommended Action Plan

### Immediate (Today)

**Apply Fix 1 (Section-Based Deduplication)** to [backend/rag/graph.py](backend/rag/graph.py#L1056-L1083):

✅ **Pro:** Simple, low-risk, backward compatible  
✅ **Impact:** Eliminates parent-child redundancy without breaking other logic  
✅ **Complexity:** 30 lines of code

### Short-term (This Week)

**Decide: Which pattern do you want?**

- **Fine-only** (highest precision, no redundancy)
- **Coarse-only** (broad context, smaller result sets)
- **Section-best** (hybrid, keep diversity)

### Medium-term (This Sprint)

**Implement Fix 2** if you choose fine-only or coarse-only pattern:
- Update [backend/rag/graph.py](backend/rag/graph.py) retrieval calls to pass `chunk_level`
- Add configuration to control default chunk level per use case (Q&A vs. summarization)

---

## 9. Testing & Validation

### Before Fix

```bash
# Retrieve a multi-paragraph section
query="attention mechanism"
results = retriever.retrieve(query, document_id=doc_id)

# Check for duplicates
sections_seen = set()
for r in results:
    section_id = r["metadata"]["section_id"]
    chunk_level = r["metadata"]["chunk_level"]
    print(f"{section_id}: {chunk_level}")
    
# Output (BEFORE FIX):
# bd077a96-5a38-5281-993e-10cf869afcde_section_1: coarse
# bd077a96-5a38-5281-993e-10cf869afcde_section_1: fine
# bd077a96-5a38-5281-993e-10cf869afcde_section_1: fine  ← BUG: Same section, 3 chunks
```

### After Fix 1

```
# bd077a96-5a38-5281-993e-10cf869afcde_section_1: coarse  ← Only 1 chunk per section
# other_section_id: fine
# another_section_id: fine
```

---

## 10. Summary Table

| Question | Answer | Evidence |
|----------|--------|----------|
| **Schema audit: Is there `chunk_type` metadata?** | ✅ Yes, `chunk_level` field | [models.py L35–45](backend/rag/retrieval/chunking/models.py#L35-L45) |
| **How are parent/child chunks created?** | Both levels from same section | [section_chunker.py L1074–1082](backend/rag/retrieval/chunking/section_chunker.py#L1074-L1082) |
| **Is there server-side filtering?** | Partial (parameter exists, rarely used) | [hybrid_retriever.py L150](backend/rag/retrieval/search/hybrid_retriever.py#L150) |
| **Is there post-retrieval deduplication?** | ✅ Yes, but insufficient | [graph.py L1890](backend/rag/graph.py#L1890) |
| **Why are parent+child chunks together?** | Jaccard threshold (0.7) too high for parent-child pairs (~0.25–0.40) | Math shown above |
| **What's the intended pattern?** | Unclear; both levels stored, no explicit separation | Inferred from architecture |
| **Is this a bug?** | ✅ **YES** — dedup should catch hierarchical redundancy | Threshold analysis |
| **How to fix?** | Section-based deduplication (minimum risk) | Fix 1 above |

---

## Files to Review/Update

1. **[backend/rag/graph.py](backend/rag/graph.py)** – Lines 1056–1083, 1890
   - Apply section-based dedup fix
   - Add configuration for chunk-level preference

2. **[backend/rag/retrieval/search/hybrid_retriever.py](backend/rag/retrieval/search/hybrid_retriever.py)** – Line 150
   - Ensure `chunk_level` parameter is enforced in retrieval calls

3. **[backend/rag/retrieval/config.py](backend/rag/retrieval/config.py)**
   - Document `FINE_CHUNK_SIZE`, `COARSE_CHUNK_SIZE` ratios
   - Add `DEFAULT_CHUNK_LEVEL` config for Q&A, guides, etc.

4. **[docs/RETRIEVAL_SYSTEM_FULL_REPORT_2026-03-29.md](docs/RETRIEVAL_SYSTEM_FULL_REPORT_2026-03-29.md)** – Architecture doc
   - Update to clarify intended chunking strategy (which pattern: fine-only, coarse-only, or hybrid?)

---

## References

- **Hierarchical Chunking Overview:** [HIERARCHICAL_CHUNKING_OVERVIEW.md](HIERARCHICAL_CHUNKING_OVERVIEW.md)
- **Retrieval System Report:** [docs/RETRIEVAL_SYSTEM_FULL_REPORT_2026-03-29.md](docs/RETRIEVAL_SYSTEM_FULL_REPORT_2026-03-29.md)
- **Deduplication Trace:** Enable LangSmith tracing to see pre/post-dedup chunk counts per query
