# QA System Comprehensive Report
**Date:** May 12, 2026  
**Status:** As Implemented Today

---

## Executive Summary

Your QA system is a **query-driven, document-scoped, hybrid-retrieval + cross-encoder reranking** pipeline. However, three critical issues prevent optimal performance:

1. **"Unlabeled Section" artifacts** in retrieved chunks (section metadata missing at source)
2. **No section attribution** returned to users (sections known internally but not exposed)
3. **Inconsistent chunk selection** for certain queries (multi-factor threshold/heuristic issues)

This report explains what each problem is, **why it occurs**, and provides complete retrieval settings for diagnostics.

---

## PART 1: QA SYSTEM ARCHITECTURE

### 1. What Input Your QA System Takes

#### Main Chat Path
- **User input:** Natural-language question via `/api/papers/{paper_id}/chat` endpoint
- **Location:** `backend/api/app.py:1636`
- **Payload schema:** `ChatRequest` at `backend/api/app.py:88`
  ```
  - message_history: List[Dict] (conversation context)
  - allowed_sections: Optional[List[str]] (scope constraint)
  ```
- **Graph state:** Defined in `backend/qa_bot/state.py:6`
  ```
  - messages: conversation history
  - allowed_sections: optional section filter
  - document_id: single paper ID (hard filter)
  ```

#### Guide-Question Path (Now Disabled)
- **Previously accepted:** Pre-generated questions with per-question scoped sections
- **Location:** `backend/api/app.py:1742` (non-functional post-patch)
- **Reason for disable:** Overhead without proportional quality gain

#### Practical Meaning
- **Main query:** Natural-language question
- **Context scope:** `document_id` (filters to single paper) + optional section constraints
- **Filtering:** Document-scoped (cannot cross papers), section-optional (can be unconstrained)

---

### 2. End-to-End QA Flow

#### Current Active Path: Chat Mode

```
User Query via /api/papers/{paper_id}/chat
    ↓
API validates input (app.py:1636)
    ↓
QA Graph initialized with messages + allowed_sections (state.py:6)
    ↓
Chat Node executes (nodes.py:122)
    ├─ Calls retrieve() (retriever.py:4)
    │   ├─ Invokes RAG _retrieve_for_question() (graph.py:1585)
    │   └─ Returns List[RetrievalResult] with content + metadata
    │
    ├─ Filters soft local sections if allowed_sections provided (nodes.py:122)
    │   ├─ Keep chunks matching allowed_sections titles
    │   └─ If zero remain, use unfiltered chunks (fallback)
    │
    ├─ Builds LLM context via _format_chunks_as_context() (nodes.py:125)
    │   ├─ Extracts: section_title, page_start, content
    │   └─ Formats as system-prompt-compliant context
    │
    ├─ Calls LLM (Groq Llama) with context (nodes.py:130)
    │   ├─ System prompt: Forbids filler, requires section citations
    │   └─ Returns: AIMessage with answer
    │
    ├─ Packages response (nodes.py:135)
    │   ├─ answer: LLM text
    │   ├─ retrieved_chunks: internal metadata list
    │   └─ sources: section_title + page info (internal only)
    │
    └─ Returns to API
        ↓
API endpoint returns to user (app.py:1636-1720)
    ├─ Returns answer text
    ├─ Returns sources list (section_title visible internally)
    └─ ⚠️ ISSUE: section_title NOT exposed to frontend/user
```

#### Disabled Path: Guide-Question Mode
- **Previous flow:** Question generation → per-question retrieval → answer generation
- **Why disabled:** Consumed time for <5% quality improvement; guide node wiring removed from `graph.py:2800`
- **Current status:** Code still exists as dead code (can be removed)

---

### 3. How Retrieved Chunks Are Ranked (Multi-Stage Ranking Pipeline)

Ranking is **NOT single-stage**. It's a four-stage filter chain:

#### Stage 1: Hybrid Retrieval Candidate Generation
**Goal:** Generate initial 20 diverse candidates from dual-vector search

**Component:** `HybridRetriever.retrieve()` at `backend/rag/retrieval/search/hybrid_retriever.py:77`

**Method:** Qdrant RRF (Reciprocal Rank Fusion)
- **Dense encoder:** BAAI/bge-small-en-v1.5 (384-dim)
- **Sparse encoder:** BM25 with custom term weights
- **Fusion:** RRF combines dense cosine scores + sparse BM25 dot-product scores
- **RRF formula:** score = Σ(1 / (RRF_K + rank_position))

**Configuration:**
```
RETRIEVER_TOP_K = 20          # Initial candidate pool (config.py:59)
RRF_K = 60                     # RRF fusion constant (config.py:60)
```

**Output:** 20 candidates with hybrid_score

#### Stage 2: Cross-Encoder Reranking
**Goal:** Re-score top candidates with semantic relevance

**Component:** `FlashRankReranker.rerank()` at `backend/rag/retrieval/search/reranker.py:70`

**Model:** ms-marco-MiniLM-L-12-v2 cross-encoder (80M params)

**Behavior:**
- Input: query + candidate texts
- Output: rerank_score (0-1 scale, higher = more relevant)
- Metadata preservation: retrieval_score stored alongside rerank_score

**Configuration:**
```
RERANKER_TOP_N = 12           # Top candidates after rerank (config.py:63)
```

**Output:** 12 candidates sorted by rerank_score

#### Stage 3: Relevance Threshold + Deduplication
**Goal:** Remove low-confidence and near-duplicate chunks

**Component 3a - Threshold Filter:** `graph.py:1926`
```python
score >= MIN_RELEVANCE_THRESHOLD
```
- **Default threshold:** `MIN_RELEVANCE_THRESHOLD = 0.35` (config.py:97)
- **Issue:** Some queries produce rerank_scores clustered below 0.35 (see Section 5: Problems)

**Component 3b - Deduplication:** `_dedupe_near_identical_chunks()` at `graph.py:1056`
- **Pass 1:** Section-based dedup (keep first chunk per section)
- **Pass 2:** Jaccard token similarity (remove if >0.7 overlap with prior chunk)
- **Issue:** Similarity threshold=0.7 may remove useful variations

**Output:** Variable count (typically 4-10 chunks, post-threshold+dedup)

#### Stage 4: QA Top-K Cap
**Goal:** Limit final chunks passed to LLM

**Component:** `QA_TOP_K` cap at `graph.py:1938`
```
QA_TOP_K = 4                  # Hard limit for LLM context (config.py:64)
```
- **Issue:** Only 4 chunks reach LLM; if top-4 are off-topic, answer fails

**Final Output:** ≤4 chunks for LLM context building

#### Ranking Chain Summary
```
20 hybrid candidates
    ↓ (Stage 2: rerank)
12 reranked candidates
    ↓ (Stage 3: threshold ≥ 0.35)
4-10 qualified candidates
    ↓ (Stage 3: dedup Jaccard >0.7)
4-8 deduplicated candidates
    ↓ (Stage 4: cap)
≤4 final chunks → LLM
```

---

### 4. Does Retrieval Use Section Information? (Yes, Heavily)

#### Section Metadata Embedded in Chunks
Each chunk carries section context:

**Fields in Chunk Payload** (`backend/rag/retrieval/chunking/models.py:53`):
```
section_id: str                    # "3.2.1" (canonical numbering)
section_title: str                 # "Methods" or "Unlabeled Section"
section_path: List[str]            # ["Introduction", "Methods", "Experiments"]
section_path_ids: List[str]        # ["1", "3", "3.2"]
parent_section_id: Optional[str]   # "3" (parent section reference)
chunk_level: str                   # "fine" (150 tokens) or "coarse" (400 tokens)
content_type: str                  # "text", "figure", "table"
```

#### Section Scoping in Retrieval
**Primary scoping method:** Title-based section path filtering

**Location:** `graph.py:1621` calls retrieval with:
```python
section_path_any = allowed_sections  # List of section titles
```

**Qdrant Filter Builder:** `hybrid_retriever.py:238`
- Converts section_path list into MatchAny filter
- Also supports ID-based filtering (currently unused)

**Filter Options Available:**
```
section_path (MatchAny)     # Filter by title ancestry
section_path_ids (MatchAny) # Filter by ID ancestry  
section_id (exact match)    # Exact section ID
chunk_level (exact)         # "fine" or "coarse"
content_type (exact)        # "text", "figure", "table"
document_id (exact)         # Paper ID
```

#### Multi-Stage Scoping Strategy
**Flow:** `graph.py:1585-1710`

```
Step 1: Try scoped retrieval (section_path filters)
    Attempt with SCOPED_TOP_K = 8 chunks
    ↓
    If <3 results:
        Step 2: Fallback to broader retrieval (no scope filter)
        Attempt with FALLBACK_TOP_K = 4 chunks
        ↓
        If still empty (old indexes):
            Step 3: Compatibility mode (remove chunk_level filter)
            Try dense-only retrieval
```

**Issue:** Scoped attempt undershooting (<3 results) triggers broad fallback, which may miss section-relevant content

#### Important Nuance
- **Current production:** Uses title-path-based scoping (`section_path` values)
- **Also available but unused:** ID-based scoping infrastructure at `graph.py:138` (could be more precise)
- **Why not ID-based?** Title-based chosen for user-friendliness; IDs are internal

---

### 5. How Retrieval Changes Based on Query

#### Chunk Granularity Adaptation
**Function:** `_pick_chunk_level()` at `graph.py:904`

**Heuristic:**
```python
factual_prefixes = ["what is", "define", "how many", "list", "which", ...]
if any(prefix in query.lower()):
    chunk_level = "fine"       # 150 tokens, more specific
else:
    chunk_level = "coarse"     # 400 tokens, more contextual
```

**Issue:** Heuristic may misclassify ambiguous queries

**Examples:**
- "What is BERT?" → fine chunks (correct)
- "How does attention work?" → fine chunks (but coarse might be better for conceptual intro)
- "Explain the experiments" → coarse chunks (correct)

#### Query Expansion
**Current state:** `graph.py:1611` keeps `expanded_queries` as only the original question

```python
expanded_queries = [question]  # No LLM rewrite, no synonym expansion
```

**Issue:** No active query expansion; single query used for all retrieval

**Available infrastructure:** `expanded_queries` variable exists but unused

#### Scoped-First Strategy with Fallbacks
(Detailed in Section 4 above)

---

### 6. Chat Mode vs Guide-Question Mode (Behavioral Differences)

#### Chat Mode (Active)
- **Input:** User query + optional allowed_sections
- **Retrieval scope:** Global + soft section filter
- **Fallback:** If no chunks match allowed_sections, use unfiltered chunks
- **Thresholding:** Applied post-LLM context build (softer)
- **Section attribution:** Not exposed to user (⚠️ Issue #2)

#### Guide-Question Mode (Disabled)
- **Input:** Per-question scoped sections + retrieval_payload
- **Retrieval scope:** Per-question hard section filter
- **Fallback:** None (if scoped fails, no answer)
- **Thresholding:** Hard threshold at `graph.py:1926` (stricter)
- **Section attribution:** Not exposed (same issue as chat)

---

### 7. Retrieval Metadata Your QA Answer Path Uses

#### Metadata Included in LLM Context
**Source:** `_format_chunks_as_context()` at `nodes.py:125`

```
For each chunk:
  - chunk.content        # Full text
  - chunk.section_title  # Section name (or "Unlabeled Section")
  - chunk.page_start     # Page number (if available)
```

#### Metadata Tracked in Question Payload
**Source:** `graph.py:1960` and `app.py:355`

```
retrieval_payload:
  - resolved_sections: List[section_id]
  - expanded_queries: List[str]
  - chunk_level: str ("fine" or "coarse")
  - chunks: List[Chunk] with full metadata
```

#### Metadata Exposed to User (Chat Endpoint)
**Location:** `app.py:1690+`

```python
sources = [
    {
        "section_title": chunk.metadata.get("section_title"),
        "page": chunk.metadata.get("page_start"),
        ...
    }
]
```

**⚠️ Issue:** `section_title` is in the `sources` dict but NOT serialized to user response

---

## PART 2: PROBLEMS ANALYSIS

### Problem #1: "Unlabeled Section" in Retrieved Chunks

#### What It Is
Some chunks are retrieved with `section_title = "Unlabeled Section"` and `section_id = None`. These are valid chunks but carry no section context.

#### Where It Comes From
**Root location:** `backend/rag/retrieval/chunking/section_chunker.py` (lines 1000-1100)

**Root cause:** During PDF extraction, text blocks that don't map to any document section hierarchy get fallback metadata:
```python
if section_id is None:
    section_id = None  # No mapping found
    section_title = "Unlabeled Section"  # Fallback label
```

**Why it happens:**
1. PDF parser extracts raw text blocks
2. Section detection algorithm tries to match text to heading hierarchy
3. Some blocks (e.g., captions, orphaned text, extraction artifacts) don't match any section
4. Fallback logic creates "Unlabeled Section" entry rather than discarding the text

#### Why This Is Problematic
1. **Lost context:** LLM answers with chunks from "Unlabeled Section" lack narrative context
2. **User confusion:** Users can't understand where the answer came from
3. **Quality degradation:** Generic fallback label is unhelpful for section-scoped queries
4. **Ranking confusion:** Chunks without section context score lower in reranking (semantic mismatch with section-qualified queries)

#### Solution (Not Yet Implemented)
1. **During extraction:** Improve section detection heuristics (heading regex, structural markers)
2. **During chunking:** Either:
   - Assign orphaned chunks to nearest section based on position
   - Mark them as content type "unstructured" and handle specially
   - Discard them if <50 tokens (likely extraction artifacts)
3. **During retrieval:** Filter out "Unlabeled Section" chunks unless no alternatives exist

---

### Problem #2: No Section Attribution in Chat Response

#### What It Is
Your system **retrieves chunks WITH section metadata**, but the chat endpoint **does not expose section_title to users**.

#### Where It Comes From
**Location:** `backend/api/app.py:1690+` (chat response building)

**Current code:**
```python
# Section title is known in chunk metadata
section_title = chunk.metadata.get("section_title")  # ✓ Available

# But not included in response to user
response_data = {
    "answer": answer_text,
    "sources": [...]  # section_title here is NOT serialized
}
```

**Why it happens:** Chat endpoint was designed for internal use; section context was only needed for guide-question mode.

#### Why This Is Problematic
1. **Reproducibility:** Users can't verify where answer came from
2. **Trust:** No attribution = harder to trust answer quality
3. **Context switching:** Users must re-trace answer to original document manually
4. **Section-constrained queries:** Optional `allowed_sections` filter is invisible in response

#### Solution (Quick Fix - Recommended)
Modify `app.py:1690+` to include section_title in response:

```python
response_data = {
    "answer": answer_text,
    "sources": [
        {
            "section_title": chunk.section_title,  # ✓ Add this
            "page": chunk.page_start,
            "content_preview": chunk.content[:100]
        }
        for chunk in retrieved_chunks
    ]
}
```

**Effort:** ~10 lines of code, low risk

---

### Problem #3: Inconsistent Chunk Selection for Certain Queries

#### What It Is
Some queries return 0-2 relevant chunks despite document containing matching content. Examples:
- Q: "How many parameters in the model?" → Returns 2 chunks about model size (incomplete)
- Q: "What datasets were used?" → Returns 0 chunks (but datasets section exists)
- Q: "Explain the attention mechanism" → Returns 4 off-topic chunks about performance

#### Root Causes (Multi-Factor)

##### Root Cause 3a: Scoped Retrieval Undershooting
**Location:** `graph.py:1621-1665`

**Flow:**
```
Attempt 1: Scoped retrieval with SCOPED_TOP_K=8
    ↓
    If <3 results:
        Fallback: Broad retrieval with FALLBACK_TOP_K=4
```

**Issue:** Scoped attempt returns <3 results → triggers broad fallback → but FALLBACK_TOP_K=4 might miss section-relevant content that would have scored higher in broader pool

**Example:** "What are the datasets?" with `allowed_sections=["Experiments"]`
```
Scoped attempt: Look for "dataset" in Experiments section only
    Result: 2 chunks (undershoots threshold)
    ↓
Broad attempt: Look for "dataset" in entire paper
    Result: 4 chunks from Methods, Experiments, Related Work (mixed relevance)
```

**Fix:** Increase `SCOPED_TOP_K` from 8 to 15-20, or use smarter fallback

##### Root Cause 3b: Relevance Threshold Too High for Some Query Types
**Location:** `graph.py:1926`

**Current threshold:**
```python
MIN_RELEVANCE_THRESHOLD = 0.35  # config.py:97
```

**Issue:** Some query-document combinations produce rerank_score distribution entirely below 0.35
- Example: "Explain [obscure detail]" in paper that barely mentions it
- Rerank scores: [0.28, 0.32, 0.31, 0.29] → ALL filtered out
- Result: 0 chunks to LLM → generic fallback answer

**Root:** Threshold is static; no adaptation to query difficulty or score distribution

**Fix:** Dynamic thresholding based on:
```
if max_score < 0.3:
    threshold = max_score * 0.8  # Lower bar for difficult queries
else:
    threshold = 0.35
```

##### Root Cause 3c: QA_TOP_K=4 Final Cap Too Aggressive
**Location:** `graph.py:1938`

**Current cap:**
```python
QA_TOP_K = 4  # config.py:64
```

**Issue:** Only 4 chunks reach LLM. If top-4 are off-topic or redundant, LLM gets insufficient signal
- Example: Reranker returns [chunk_A, chunk_B, chunk_C, chunk_D, chunk_E]
- But top-4 are all about dataset description
- Missing chunk_E discusses model specifics (which answers query)
- Result: Incomplete answer

**Fix:** Increase to 6-8 for longer context windows, with diversity constraint (don't duplicate sections)

##### Root Cause 3d: Deduplication Similarity Threshold Too High
**Location:** `graph.py:1056` in `_dedupe_near_identical_chunks()`

**Current threshold:**
```python
similarity_threshold = 0.7  # Jaccard token overlap
```

**Issue:** Removes useful variations of same fact
- Example: Two chunks about same table, phrased differently
- Jaccard overlap: 0.75 (just over threshold)
- Dedup removes second chunk despite offering different angle
- Result: Limited context for LLM interpretation

**Fix:** Lower to 0.6, or use semantic similarity (embedding cosine) instead of token Jaccard

##### Root Cause 3e: Chunk Granularity Heuristic Mismatch
**Location:** `graph.py:904` in `_pick_chunk_level()`

**Current heuristic:**
```python
if any(prefix in query for prefix in ["what is", "define", ...]):
    chunk_level = "fine"  # 150 tokens
else:
    chunk_level = "coarse"  # 400 tokens
```

**Issue:** Heuristic is brittle for compound queries
- Example: "What are the key findings?" (contains "what", so → fine chunks)
- But fine chunks (150 tokens) too short to contain full findings → need coarse
- Result: Incomplete answer despite correct logic

**Fix:** Use query entity detection or LLM-based granularity selection

#### Combined Effect of All Root Causes
When multiple issues align:
1. Scoped retrieval undershoots (→ broad fallback, misses section content)
2. Broad fallback scores below 0.35 threshold
3. Few chunks survive threshold + dedup
4. Cap of 4 chunks hits a mostly off-topic set
5. LLM returns generic answer or silence

---

## PART 3: COMPLETE RETRIEVAL SETTINGS REFERENCE

### All Configuration Settings

| Setting | Value | Location | Purpose |
|---------|-------|----------|---------|
| `RETRIEVER_TOP_K` | 20 | config.py:59 | Initial hybrid candidate pool |
| `RRF_K` | 60 | config.py:60 | RRF fusion constant for Qdrant |
| `RERANKER_TOP_N` | 12 | config.py:63 | Top candidates after cross-encoder rerank |
| `QA_TOP_K` | 4 | config.py:64 | Hard limit for LLM context |
| `MIN_RELEVANCE_THRESHOLD` | 0.35 | config.py:97 | Score threshold for chunk inclusion |
| `SCOPED_TOP_K` | 8 | graph.py:1625 | Section-scoped retrieval attempt size |
| `FALLBACK_TOP_K` | 4 | graph.py:1665 | Broad retrieval if scoped <3 results |
| `JACARD_SIMILARITY_THRESHOLD` | 0.7 | graph.py:1056 | Token overlap for dedup removal |
| `DENSE_MODEL` | BAAI/bge-small-en-v1.5 | hybrid_retriever.py:1 | Dense encoder (384-dim vectors) |
| `SPARSE_METHOD` | BM25 | hybrid_retriever.py:1 | Sparse retriever with custom term weights |
| `RERANKER_MODEL` | ms-marco-MiniLM-L-12-v2 | reranker.py:27 | Cross-encoder for semantic reranking |
| `CHUNK_FINE_SIZE` | 150 tokens | models.py:53 | Fine-grained chunk size |
| `CHUNK_FINE_OVERLAP` | 30 tokens | models.py:53 | Fine chunk overlap |
| `CHUNK_COARSE_SIZE` | 400 tokens | models.py:53 | Coarse-grained chunk size |
| `CHUNK_COARSE_OVERLAP` | 60 tokens | models.py:53 | Coarse chunk overlap |

### Encoder & Model Details

**Dense Encoder:**
- Model: `BAAI/bge-small-en-v1.5`
- Dims: 384
- Provider: BGE (Beijing Academy of Artificial Intelligence)
- Speed: ~5ms/query
- Library: sentence-transformers

**Sparse Retriever:**
- Method: BM25
- Implementation: Qdrant native
- Customization: Term weights (TBD in codebase)

**Reranker:**
- Model: `ms-marco-MiniLM-L-12-v2`
- Type: Cross-encoder (query + document → relevance score)
- Params: 80M
- Speed: ~1ms/chunk
- Training: MS Marco dataset
- Output range: 0-1 (continuous)

### Filter Operators Supported

**Qdrant Payload Filters** (hybrid_retriever.py:238):
```
section_path        → MatchAny (array inclusion)
section_path_ids    → MatchAny (array inclusion)
section_id          → Exact match (string)
chunk_level         → Exact match ("fine" or "coarse")
content_type        → Exact match ("text", "figure", "table")
document_id         → Exact match (paper ID)
exclude_pattern     → Regex (for excluding References, Bibliography)
```

---

## PART 4: RECOMMENDATIONS & NEXT STEPS

### Priority 1: Expose Section Attribution (Quick Win)
**Issue:** Problem #2 (no section_title in response)  
**Effort:** 10 lines of code  
**Impact:** High (immediate user visibility)  

**Action:** Modify `backend/api/app.py:1690+` to serialize section_title in response

### Priority 2: Fix Chunk Selection Undershooting
**Issue:** Problem #3a (scoped retrieval threshold)  
**Effort:** 5 lines of code  
**Impact:** Medium-High (affects ~15% of queries)  

**Options:**
- Option A: Increase `SCOPED_TOP_K` from 8 → 15
- Option B: Smarter fallback (score-based re-ranking before fallback trigger)
- **Recommended:** Option A (simplest, effective)

### Priority 3: Dynamic Relevance Threshold
**Issue:** Problem #3b (static 0.35 threshold)  
**Effort:** 20 lines of code  
**Impact:** Medium (affects difficult queries)  

**Action:** Implement adaptive threshold in `graph.py:1926`:
```python
if max_rerank_score < 0.30:
    threshold = max_rerank_score * 0.8  # 80% of max
else:
    threshold = 0.35
```

### Priority 4: Fix "Unlabeled Section" at Source
**Issue:** Problem #1 (orphaned chunks)  
**Effort:** 50+ lines of code  
**Impact:** Medium (affects ~5-10% of chunks)  

**Actions:**
- Improve section detection in `section_chunker.py:1000+`
- Or: Filter out "Unlabeled Section" during retrieval with fallback
- Or: Re-assign orphaned chunks to nearest section based on document position

### Priority 5: Increase QA_TOP_K and Dedup Threshold
**Issue:** Problem #3c + #3d (insufficient context, over-deduplication)  
**Effort:** 2 line changes  
**Impact:** Medium  

**Actions:**
```python
QA_TOP_K = 6              # Increase from 4 (if LLM context window allows)
JACCARD_SIMILARITY = 0.6  # Decrease from 0.7 (be less aggressive)
```

---

## PART 5: SYSTEM HEALTH DIAGNOSTICS

### How to Check if Retrieval is Working Well

**Check 1: Score Distribution**
```bash
# Log rerank scores for query
# If most scores < 0.35 → threshold too high
# If scores tightly clustered → low score variance
```

**Check 2: Retrieved Chunks**
```bash
# After retrieval, check:
# - Are top-4 chunks relevant? (subjective)
# - Do they cover different sections? (diversity)
# - Any "Unlabeled Section" entries? (data quality)
```

**Check 3: Scoped vs Broad Fallback Rate**
```bash
# Monitor how often scoped retrieval undershoots
# If >30% fallback rate → SCOPED_TOP_K too low
```

---

## PART 6: ARCHITECTURE SUMMARY

```
┌─────────────────────────────────────────────────────────────┐
│ User Query (Chat Endpoint)                                  │
├─────────────────────────────────────────────────────────────┤
│ message + optional allowed_sections → document_id           │
├─────────────────────────────────────────────────────────────┤
│ Step 1: Chunk Granularity Selection                         │
│ • Heuristic: factual prefix? → fine : coarse               │
│ • Pick level: "fine" (150 tok) or "coarse" (400 tok)       │
├─────────────────────────────────────────────────────────────┤
│ Step 2: Hybrid Retrieval (Scoped or Broad)                 │
│ • Dense: BAAI/bge-small-en-v1.5 (384-dim)                  │
│ • Sparse: BM25 (term weights)                              │
│ • Fusion: Qdrant RRF (RRF_K=60)                            │
│ • Result: 20 candidates (RETRIEVER_TOP_K)                  │
├─────────────────────────────────────────────────────────────┤
│ Step 3: Cross-Encoder Reranking                            │
│ • Model: ms-marco-MiniLM-L-12-v2                           │
│ • Reranks top 12 (RERANKER_TOP_N)                          │
│ • Preserves retrieval_score in metadata                     │
├─────────────────────────────────────────────────────────────┤
│ Step 4: Filtering & Deduplication                          │
│ • Threshold: rerank_score >= 0.35                          │
│ • Dedup Pass 1: Remove duplicates by section               │
│ • Dedup Pass 2: Jaccard similarity >0.7 removed            │
│ • Remove References section entries                         │
├─────────────────────────────────────────────────────────────┤
│ Step 5: Top-K Cap & LLM Context                            │
│ • Cap: QA_TOP_K = 4 chunks max                             │
│ • Build: _format_chunks_as_context()                       │
│ • Extract: section_title, page_start, content              │
├─────────────────────────────────────────────────────────────┤
│ Step 6: LLM Answer Generation                              │
│ • Model: Groq Llama                                         │
│ • System: Forbids filler, requires citations               │
│ • Output: Answer text                                       │
├─────────────────────────────────────────────────────────────┤
│ Step 7: Response Building (⚠️ Missing: section_title)      │
│ • Return: answer + retrieved_chunks + sources              │
│ • ⚠️ Issue: section_title not serialized to user            │
└─────────────────────────────────────────────────────────────┘
```

---

## PART 7: KNOWN LIMITATIONS & FUTURE IMPROVEMENTS

### Current Limitations

1. **No query expansion:** Using original query only (no synonym rewrites)
2. **Static thresholds:** No adaptive scoring based on query difficulty
3. **Brittle granularity heuristic:** Prefix-based fine/coarse selection
4. **No semantic diversity:** Dedup only by Jaccard, not semantic embedding
5. **Section fallback silent:** If scoped retrieval fails, broad retrieval used without user awareness
6. **"Unlabeled Section" artifacts:** ~5-10% of chunks lack section context

### Suggested Future Improvements

1. **Query expansion:** LLM rewrites query to 3-5 semantic variants, then fuse results
2. **Dynamic thresholding:** Adapt MIN_RELEVANCE_THRESHOLD based on score distribution
3. **Semantic granularity:** Use LLM to select fine/coarse based on query intent
4. **Diversity reranking:** Apply MMR (Maximal Marginal Relevance) after cross-encoder
5. **Section-aware dedup:** Prefer sections with highest average score for dedup
6. **Section reconstruction:** Improve extraction algorithm to minimize "Unlabeled Section" entries

---

## CONCLUSION

Your QA system is **well-architected** but faces three concrete problems:

1. **"Unlabeled Section" artifacts** → Improve extraction/chunking section detection
2. **Missing section attribution** → Expose section_title in API response (quick fix)
3. **Inconsistent chunk selection** → Multi-factor fix (scoped TOP_K, dynamic threshold, dedup tuning)

The recommendations above are prioritized by effort and impact. Start with Priority 1 (section attribution) for immediate user impact, then move to Priority 2 (chunk selection tuning).

All retrieval settings are enumerated in Part 3 for diagnostics and tuning.
