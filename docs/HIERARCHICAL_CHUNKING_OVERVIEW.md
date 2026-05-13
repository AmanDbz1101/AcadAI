# Hierarchical Chunking RAG Pipeline - Comprehensive Analysis

**Date**: May 10, 2026  
**Project**: Research Paper Assistant  
**Analysis Scope**: Chunk construction, vector store schema, retrieval, deduplication

---

## 1. CHUNK CONSTRUCTION & INGESTION

### 1.1 Section Hierarchy Foundation

Sections are first detected and organized into a hierarchical tree structure:

**Key File**: [backend/extraction/models/section_hierarchy.py](backend/extraction/models/section_hierarchy.py)

```python
class SectionNode(BaseModel):
    """Represents a single section in the document hierarchy."""
    
    # Identification
    section_id: str                    # Unique ID (e.g., "3.2.1" or UUID)
    title: str                         # Section heading text
    
    # Hierarchy information
    level: int                         # Depth (1=top-level, 6=deepest)
    numbering: Optional[str]           # Section number (e.g., "1.2.3")
    parent_id: Optional[str]           # Parent section ID
    child_section_ids: List[str]       # List of child section IDs
    has_subsections: bool              # Boolean flag
    
    # Position metadata
    page_start: int                    # Starting page
    page_end: Optional[int]            # Ending page
    reading_order: int                 # Position in document
    
    # Content classification
    section_type: str                  # e.g., "standard", "abstract", "references"
```

**Hierarchy Navigation Methods**:
```python
class SectionHierarchy(BaseModel):
    sections: List[SectionNode]        # All sections in reading order
    root_sections: List[str]           # Top-level section IDs
    total_sections: int                # Total count
    max_depth: int                     # Maximum nesting level
    
    # Navigation API
    def get_section(section_id: str) -> Optional[SectionNode]
    def get_children(section_id: str) -> List[SectionNode]
    def get_parent(section_id: str) -> Optional[SectionNode]
    def get_ancestors(section_id: str) -> List[SectionNode]        # Full ancestry chain
    def get_descendants(section_id: str) -> List[SectionNode]      # All descendants
    def get_section_path(section_id: str) -> List[SectionNode]     # Root to section
```

**Construction Flow** (in [backend/extraction/app/section_detector.py](backend/extraction/app/section_detector.py)):

```
1. Extract sections from PDF using Docling
2. Detect heading levels via typography/patterns
3. Build parent-child relationships using level-based stack
4. Compute section_path and section_path_ids (ancestry chains)
5. Assign section_id (using numbering if available, else UUID-based)
```

### 1.2 Chunk Creation from Sections

**Key File**: [backend/rag/retrieval/chunking/section_chunker.py](backend/rag/retrieval/chunking/section_chunker.py)

The `chunk_paper()` function splits section text into token-aware chunks:

```python
def chunk_paper(
    sections: list[dict],           # From section hierarchy
    paper_id: str,
    chunk_size: int = 400,          # COARSE_CHUNK_SIZE
    overlap: int = 60,              # COARSE_CHUNK_OVERLAP
    model_name: str = "bge-small-en-v1.5",
) -> list[Chunk]:
    """
    Split sections into chunks with full hierarchy context.
    
    Algorithm:
    1. Build sections_by_id dict for O(1) parent lookups
    2. For each section:
       a. Build canonical_section_id (from numbering or section_id)
       b. Build section_path (list of ancestor titles)
       c. Build section_path_ids (list of ancestor IDs for filtering)
       d. Split text using TokenAwareSplitter
       e. For each text window:
          - Create Chunk with all hierarchy metadata
          - Assign deterministic UUID: uuid5(namespace, paper_id:chunk_index)
    """
```

### 1.3 Chunk Data Model

**Key File**: [backend/rag/retrieval/chunking/models.py](backend/rag/retrieval/chunking/models.py)

```python
class Chunk(BaseModel):
    """A single indexable unit carrying full section context."""
    
    # ── Identity ────────────────────────────────────────────────────────
    chunk_id: str                      # UUID (deterministic, not random)
    document_id: str                   # Parent document UUID
    
    # ── Content ─────────────────────────────────────────────────────────
    content: str                       # Raw text content
    original_content: Optional[str]    # Original before transformation
    image_path: Optional[str]          # Path to figure image (if figure)
    content_type: str                  # "text", "table", or "figure"
    token_count: int                   # Estimated token count
    chunk_index: int                   # Zero-based index in document
    chunk_level: str                   # "fine" (150 tokens) or "coarse" (400 tokens)
    
    # ── Section Context (HIERARCHICAL) ──────────────────────────────────
    section_id: Optional[str]          # Immediate section ID (e.g., "3.2.1")
    section_title: str                 # Title of containing section
    section_level: int                 # Heading depth (1 = top-level)
    section_numbering: Optional[str]   # Dotted numbering (e.g., "3.2.1")
    
    section_path: list[str]            # BREADCRUMB TITLES
                                       # ["Model Architecture", "Attention", "Multi-Head"]
    
    section_path_ids: list[str]        # ANCESTRY CHAIN FOR FILTERING
                                       # ["3", "3.2", "3.2.1"]
    
    parent_section_id: Optional[str]   # Immediate parent ID
    
    # ── Location ────────────────────────────────────────────────────────
    page_start: Optional[int]          # First page of source section
    page_end: Optional[int]            # Last page of source section
    
    # ── Element References ──────────────────────────────────────────────
    element_ids: list[str]             # Docling element IDs (cross-reference)
    source_file: Optional[str]         # Relative path to source
    
    def to_payload(self) -> dict:
        """Serialize to flat Qdrant payload dict."""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "content": self.content,
            "content_type": self.content_type,
            "chunk_level": self.chunk_level,
            "section_id": self.section_id,
            "section_title": self.section_title,
            "section_path": self.section_path,      # Array of strings
            "section_path_ids": self.section_path_ids,  # Array of IDs (KEY FOR HIERARCHY)
            "parent_section_id": self.parent_section_id,
            "page_start": self.page_start,
            "page_end": self.page_end,
            # ... other fields
        }
```

### 1.4 Example Chunk Structure

Given a paper with sections:
```
1. Introduction
2. Background
   2.1. Related Work
   2.2. Preliminaries
3. Methodology
   3.1. Dataset
   3.2. Models
      3.2.1. Transformer Architecture
      3.2.2. Attention Mechanism
```

A chunk from section 3.2.1 would have:

```python
chunk = Chunk(
    chunk_id="uuid5-deterministic",
    document_id="paper-uuid",
    content="Transformer uses self-attention layers...",
    content_type="text",
    chunk_level="coarse",
    section_id="3.2.1",
    section_title="Transformer Architecture",
    section_level=3,
    section_numbering="3.2.1",
    
    section_path=["Methodology", "Models", "Transformer Architecture"],
    section_path_ids=["3", "3.2", "3.2.1"],      # ← KEY: enables parent filtering
    parent_section_id="3.2",
    
    page_start=5,
    page_end=6,
)
```

**Key Insight**: 
- **section_path_ids** is an array from root to leaf of section IDs
- This allows filtering: "show all chunks under section 3.2" matches both "3.2" and "3.2.1"
- **parent_section_id** is the immediate parent

---

## 2. VECTOR STORE SCHEMA (Qdrant)

### 2.1 Collection Configuration

**Key File**: [backend/rag/retrieval/indexing/qdrant_store.py](backend/rag/retrieval/indexing/qdrant_store.py)

```python
# Collection: "research_papers"
# Vectors: Named vectors (hybrid retrieval)

Vectors Config:
├── dense
│   ├── Type: VectorParams
│   ├── Size: 384 dimensions
│   ├── Distance: COSINE
│   └── Model: BAAI/bge-small-en-v1.5
│
└── sparse
    ├── Type: SparseVectorParams
    ├── Encoding: BM25 (per-document fitted)
    ├── Distance: DOT product (inner-product)
    └── Index: On-disk=False (for speed)
```

### 2.2 Payload Indexes (Search Filters)

Qdrant creates indexes on these payload fields for fast filtering:

```python
# MANDATORY INDEXES
document_id             → KEYWORD (exact match filter)
section_title           → TEXT (full-text filter via MatchText)
section_path            → KEYWORD (array of section titles)
chunk_level             → KEYWORD (fine/coarse)
content_type            → KEYWORD (text/figure/table)

# HIERARCHY-SPECIFIC INDEXES
section_id              → KEYWORD (immediate section ID)
parent_section_id       → KEYWORD (parent ID for hierarchy filtering)
section_path_ids        → KEYWORD (array of ancestor IDs - CRITICAL)
                          └─ Enables "show all chunks under section 3.2"
```

### 2.3 Complete Payload Structure

Each point in Qdrant has this payload:

```python
{
    # Identity
    "chunk_id": "uuid",
    "document_id": "uuid",
    
    # Content
    "content": "...",                       # Indexed for dense/sparse search
    "original_content": "...",              # Pre-transformation (tables)
    "image_path": "...",                    # Figure path (optional)
    "content_type": "text|table|figure",    # ← Indexed
    "token_count": 156,
    "chunk_index": 42,
    "chunk_level": "coarse|fine",           # ← Indexed
    
    # Section Hierarchy (CRITICAL)
    "section_id": "3.2.1",                  # ← Indexed
    "section_title": "Multi-Head Attention", # ← Indexed (TEXT)
    "section_level": 3,
    "section_numbering": "3.2.1",
    "section_path": [
        "Methodology",                      # ← Indexed (KEYWORD array)
        "Models",
        "Transformer Architecture"
    ],
    "section_path_ids": [
        "3",                                # ← Indexed (KEYWORD array) - MOST IMPORTANT
        "3.2",
        "3.2.1"
    ],
    "parent_section_id": "3.2",             # ← Indexed
    
    # Location
    "page_start": 5,
    "page_end": 6,
    
    # Cross-reference
    "element_ids": ["docling_elem_123"],
    "source_file": "paper.pdf"
}
```

### 2.4 Indexing Process

**Key File**: [backend/rag/retrieval/indexing/indexer.py](backend/rag/retrieval/indexing/indexer.py)

```python
def index_document(hierarchy_json_path, output_dir, pdf_path):
    """
    Pipeline: Chunks → Dense Embed → Sparse Embed → Qdrant Upsert
    """
    
    # 1. Chunk the document
    chunks: list[Chunk] = chunker.chunk_document(
        hierarchy_json_path=hierarchy_json_path,
        pdf_path=pdf_path,
    )
    
    # 2. Fit per-document BM25 encoder
    corpus = [c.content for c in chunks]
    sparse_enc = BM25SparseEncoder()
    sparse_enc.fit(corpus)
    sparse_enc.save(f"{document_id}_bm25.pkl")  # Save for query time
    
    # 3. Encode
    dense_vecs = dense_encoder.encode_documents(corpus)      # (N, 384)
    sparse_vecs = sparse_enc.embed_documents(corpus)         # list[SparseVector]
    
    # 4. Batch upsert to Qdrant
    for batch in chunks_batched(chunks, batch_size=64):
        points = [
            PointStruct(
                id=uuid5(namespace, f"{doc_id}:{chunk_index}"),  # Deterministic
                payload=chunk.to_payload(),                      # Flat dict
                vector={
                    "dense": dense_vecs[i].tolist(),
                    "sparse": {"indices": sv.indices, "values": sv.values},
                },
            )
            for i, chunk in enumerate(batch)
        ]
        client.upsert(collection_name, points=points)
```

**Key Point**: UUIDs are deterministic (uuid5), so re-indexing overwrites rather than duplicates.

---

## 3. RETRIEVAL IMPLEMENTATION

### 3.1 Retrieval Pipeline Entry Point

**Key File**: [backend/rag/retrieval/pipeline.py](backend/rag/retrieval/pipeline.py)

```python
class RetrievalPipeline:
    """Top-level orchestrator for hybrid retrieval + reranking."""
    
    def query(
        self,
        query: str,
        document_id: Optional[str] = None,
        section_id: Optional[str] = None,           # For scoped retrieval
        section_path_ids_any: Optional[list[str]] = None,  # Hierarchy filter
        chunk_level: Optional[str] = None,
        content_type: Optional[str] = None,
        top_k: int = 20,                           # Candidates before rerank
        top_n: int = 12,                           # Final results after rerank
        rerank: bool = True,
        exclude_reference_sections: bool = True,
    ) -> list[RetrievalResult]:
        """
        1. Retrieve candidates via hybrid search
        2. Optionally rerank with cross-encoder
        3. Return top-N results
        """
        
        # Load BM25 encoder for this document
        sparse_enc = self._get_sparse_encoder(document_id)
        
        # Run hybrid retrieval
        retriever = HybridRetriever(
            store_manager=store_manager,
            dense_encoder=dense_encoder,
            sparse_encoder=sparse_enc,
            top_k=top_k,
        )
        
        candidates = retriever.retrieve(
            query=query,
            document_id=document_id,
            section_path_ids_any=section_path_ids_any,  # ← Hierarchy filter
            # ... other filters
        )
        
        # Rerank if enabled
        if rerank:
            results = self.rerank_results(query, candidates, top_n=top_n)
        else:
            results = candidates[:top_n]
        
        return results
```

### 3.2 Hybrid Retriever (Dense + Sparse)

**Key File**: [backend/rag/retrieval/search/hybrid_retriever.py](backend/rag/retrieval/search/hybrid_retriever.py)

```python
class HybridRetriever:
    """
    Hybrid (dense + sparse) search backed by Qdrant.
    
    Flow:
    1. Build Qdrant Filter from parameters
    2. Encode query to dense + sparse vectors
    3. Run Qdrant similarity_search_with_score (with RRF fusion)
    4. Map results to RetrievalResult
    """
    
    def retrieve(
        self,
        query: str,
        document_id: Optional[str] = None,
        section_path_ids_any: Optional[list[str]] = None,  # ← Hierarchy
        section_id: Optional[str] = None,
        chunk_level: Optional[str] = None,
        content_type: Optional[str] = None,
        exclude_reference_sections: bool = True,
    ) -> list[RetrievalResult]:
        
        # Build Qdrant filter
        payload_filter = self._build_filter(
            document_id,
            section_path_ids_any=section_path_ids_any,  # KEY
            chunk_level=chunk_level,
            content_type=content_type,
            # ...
        )
        
        # Hybrid search with RRF fusion
        hits = self._hybrid_search(query, payload_filter)
        
        # Convert to RetrievalResult
        results = [
            RetrievalResult(
                content=doc.page_content,
                score=score,
                metadata=doc.metadata,
            )
            for doc, score in hits
        ]
        
        return results
```

### 3.3 Filter Builder (Hierarchy-Aware)

```python
@staticmethod
def _build_filter(
    document_id: Optional[str],
    section_path_ids_any: Optional[list[str]] = None,
    chunk_level: Optional[str] = None,
    content_type: Optional[str] = None,
    # ...
) -> Filter:
    """Build Qdrant Filter with hierarchy support."""
    
    conditions = []
    
    # Document filter
    if document_id:
        conditions.append(FieldCondition(
            key="document_id",
            match=MatchValue(value=document_id),
        ))
    
    # ← CRITICAL: Hierarchy filter using section_path_ids array
    if section_path_ids_any:
        conditions.append(FieldCondition(
            key="section_path_ids",           # Array of IDs
            match=MatchAny(any=section_path_ids_any),  # Parent "3.2" matches ["3.2", "3.2.1", ...]
        ))
    
    # Other filters
    if chunk_level:
        conditions.append(FieldCondition(
            key="chunk_level",
            match=MatchValue(value=chunk_level),
        ))
    
    if content_type:
        conditions.append(FieldCondition(
            key="content_type",
            match=MatchValue(value=content_type),
        ))
    
    return Filter(must=conditions or None)
```

### 3.4 Section-Scoped Retrieval

**Key File**: [backend/rag/graph.py](backend/rag/graph.py) (lines 138-198)

```python
def _retrieve_with_section_id_scope(
    state: dict,
    pipeline: RetrievalPipeline,
) -> dict:
    """
    Retrieve chunks scoped to a specific section and its descendants.
    
    Parent sections automatically include all descendants (e.g., section 3.2
    matches both 3.2 and 3.2.1).
    """
    section_id = state.get("target_section_id")
    document_id = state.get("document_id")
    query = state.get("question")
    
    # ← Uses section_path_ids array for MatchAny filter
    results = pipeline.retrieve_with_section_scope(
        query=query,
        section_id=section_id,
        document_id=document_id,
        top_k=20,
        rerank=True,
    )
    
    return {
        **state,
        "retrieved_chunks": results,
        "retrieval_count": len(results),
    }
```

### 3.5 Multi-Stage Retrieval in QA Pipeline

**Key File**: [backend/rag/graph.py](backend/rag/graph.py) (lines 1543-1700)

```python
@traceable(name="_retrieve_for_question", run_type="chain")
def _retrieve_for_question(
    question: str,
    document_id: str,
    section_id: Optional[str],
    pipeline: RetrievalPipeline,
) -> tuple[list[RetrievalResult], dict]:
    """
    Multi-stage retrieval with fallback:
    
    Stage 1: Scoped retrieval (within target section and descendants)
    Stage 2: Fallback if under-recovered (broader retrieval)
    Stage 3: Compatibility retrieval (if fallback also fails)
    """
    
    # STAGE 1: Scoped (section_id present → filter by section_path_ids)
    if section_id:
        scoped_hits = pipeline.retrieve_with_section_scope(
            query=question,
            section_id=section_id,
            document_id=document_id,
            top_k=8,
        )
        if len(scoped_hits) >= 2:
            return scoped_hits, {"strategy": "scoped", "resolved_sections": [section_id]}
    
    # STAGE 2: Fallback (broader search without section filter)
    fallback_hits = pipeline.query(
        query=question,
        document_id=document_id,
        top_k=4,
        rerank=True,
    )
    if len(fallback_hits) >= 2:
        return fallback_hits, {"strategy": "fallback"}
    
    # STAGE 3: Compatibility (last resort)
    compatibility_hits = pipeline.query(
        query=question,
        document_id=document_id,
        top_k=10,
        rerank=False,  # Skip rerank to maximize recall
    )
    return compatibility_hits, {"strategy": "compatibility"}
```

---

## 4. DEDUPLICATION LOGIC

### 4.1 Exact ID Deduplication

**Key File**: [backend/rag/graph.py](backend/rag/graph.py) (lines 1035-1053)

```python
def _dedupe_results(results: list[Any]) -> list[Any]:
    """
    Remove duplicate results by chunk_id (fallback: content prefix).
    
    When the same chunk appears in results from different retrieval
    stages/strategies, keep only the highest-scoring version.
    """
    best_by_key: dict[str, Any] = {}
    
    for result in results:
        metadata = result.metadata or {}
        chunk_id = metadata.get("chunk_id")
        
        if chunk_id:
            key = f"id:{chunk_id}"  # Use chunk_id as key
        else:
            key = f"text:{result.content[:200]}"  # Fallback: first 200 chars
        
        existing = best_by_key.get(key)
        if existing is None or result.score > existing.score:
            # Keep result with higher score
            best_by_key[key] = result
    
    deduped = list(best_by_key.values())
    deduped.sort(key=_result_score, reverse=True)
    return deduped
```

**Usage in QA Pipeline**:
```python
# Merge results from multiple retrieval strategies
merged_hits = _dedupe_results(scoped_hits + fallback_hits)
```

### 4.2 Near-Duplicate Suppression (Token-Overlap Jaccard)

**Key File**: [backend/rag/graph.py](backend/rag/graph.py) (lines 1056-1083)

```python
def _dedupe_near_identical_chunks(
    chunks: list[Any],
    similarity_threshold: float = 0.7,
) -> list[Any]:
    """
    Remove near-identical chunks using token-overlap Jaccard similarity.
    
    Prevents parent+child chunk pairs from appearing together.
    
    Algorithm:
    1. For each chunk, tokenize content to word set
    2. Compute Jaccard similarity against previously kept chunks
    3. If Jaccard > 0.7, skip (likely duplicate/near-duplicate)
    4. Otherwise, add to deduped list
    """
    deduped_chunks: list[Any] = []
    deduped_token_sets: list[set[str]] = []
    
    for chunk in chunks:
        # Tokenize chunk content
        chunk_tokens = set(chunk.content.split())
        is_duplicate = False
        
        # Check against all previously kept chunks
        for kept_tokens in deduped_token_sets:
            union = chunk_tokens | kept_tokens
            if not union:
                jaccard = 1.0
            else:
                intersection = chunk_tokens & kept_tokens
                jaccard = len(intersection) / len(union)
            
            # If Jaccard > 0.7, consider it a duplicate
            if jaccard > similarity_threshold:
                is_duplicate = True
                break
        
        if not is_duplicate:
            deduped_chunks.append(chunk)
            deduped_token_sets.append(chunk_tokens)
    
    return deduped_chunks
```

**Usage in QA Pipeline** (lines 1890):
```python
# Apply both deduplication layers
filtered_hits = [
    chunk for chunk in hits if _result_score(chunk) >= MIN_RELEVANCE_THRESHOLD
]
deduped_hits = _dedupe_near_identical_chunks(filtered_hits)
top_hits = deduped_hits[:QA_TOP_K]  # Keep top 4
```

### 4.3 Reference Section Filtering

**Key File**: [backend/rag/retrieval/search/hybrid_retriever.py](backend/rag/retrieval/search/hybrid_retriever.py)

```python
# Filter pattern
_REFERENCE_SECTION_HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*)?\s*[:.)-]?\s*(?:references?|bibliography|works cited)\b",
    flags=re.IGNORECASE,
)

# In retrieval
if exclude_reference_sections:
    filtered = [
        result
        for result in results
        if not self._metadata_is_reference_section(result.metadata)
    ]
```

### 4.4 Post-Processing Pipeline Summary

```
Retrieved Chunks (top_k=20)
    ↓
_dedupe_results() by chunk_id
    ↓
Filter references (exclude_reference_sections=True)
    ↓
Filter by relevance score (threshold=0.35)
    ↓
_dedupe_near_identical_chunks() (Jaccard > 0.7)
    ↓
Take top-N (QA_TOP_K=4) for QA context
```

---

## 5. HIERARCHICAL FILTERING IN ACTION

### 5.1 Example: Retrieving "all chunks under section 3.2"

**Given section hierarchy**:
```
3. Methodology
   3.1. Dataset (section_id="3.1", section_path_ids=["3", "3.1"])
   3.2. Models (section_id="3.2", section_path_ids=["3", "3.2"])
      3.2.1. Attention (section_id="3.2.1", section_path_ids=["3", "3.2", "3.2.1"])
      3.2.2. Transformer (section_id="3.2.2", section_path_ids=["3", "3.2", "3.2.2"])
```

**Query with section_id="3.2"**:

```python
pipeline.retrieve_with_section_scope(
    query="how does attention work?",
    section_id="3.2",  # ← Request section 3.2
)

# Internally builds filter:
Filter(
    must=[
        FieldCondition(
            key="section_path_ids",
            match=MatchAny(any=["3.2"])  # ← Matches any path containing "3.2"
        ),
        FieldCondition(
            key="document_id",
            match=MatchValue(value=document_id),
        ),
    ]
)

# Qdrant returns:
# ✓ Chunks from 3.2.1 (section_path_ids=["3", "3.2", "3.2.1"] contains "3.2")
# ✓ Chunks from 3.2.2 (section_path_ids=["3", "3.2", "3.2.2"] contains "3.2")
# ✗ Chunks from 3.1 (section_path_ids=["3", "3.1"] does NOT contain "3.2")
```

**Why this works**:
- `section_path_ids` is an array stored in Qdrant
- `MatchAny` filter checks if requested ID exists anywhere in the array
- Parent "3.2" implicitly includes all descendants "3.2.1", "3.2.2", etc.

### 5.2 Parent vs Child Chunk Distinction

**Scenario**: Both parent chunk (section 3.2) and child chunk (section 3.2.1) retrieved

```python
parent_chunk = {
    "section_id": "3.2",
    "section_path_ids": ["3", "3.2"],
    "section_title": "Models",
    "content": "Models are the core components. We use attention and transformers...",
}

child_chunk = {
    "section_id": "3.2.1",
    "section_path_ids": ["3", "3.2", "3.2.1"],
    "section_title": "Attention",
    "content": "Attention mechanism allows the model to focus on relevant parts...",
}

# Near-duplicate detection:
parent_tokens = {"Models", "are", "the", "core", "components", ...}
child_tokens = {"Attention", "mechanism", "allows", "model", "to", "focus", ...}

# Compute Jaccard
common = {"model", "to"}
union = {...all unique tokens...}
jaccard = 2 / 50 ≈ 0.04

# Result: NOT a duplicate (0.04 < 0.7), both kept
```

**If content heavily overlaps** (e.g., child chunk replicates parent):

```python
parent_tokens = {"attention", "mechanism", "uses", "self", "attention", ...}
child_tokens = {"attention", "mechanism", "uses", "self", "attention", "specifically", ...}

jaccard ≈ 0.8  # > 0.7

# Result: IS a duplicate, child skipped to avoid redundancy
```

---

## 6. CONFIGURATION PARAMETERS

### Chunking
```python
FINE_CHUNK_SIZE = 150       # tokens
FINE_CHUNK_OVERLAP = 30     # tokens
COARSE_CHUNK_SIZE = 400     # tokens
COARSE_CHUNK_OVERLAP = 60   # tokens
CHUNK_MIN_CHARS = 80        # minimum content size
```

### Retrieval & Ranking
```python
RETRIEVER_TOP_K = 20        # candidates before rerank
RERANKER_TOP_N = 12         # final results after rerank
SCOPED_TOP_K = 8            # for section-scoped retrieval
FALLBACK_TOP_K = 4          # broader fallback
QA_TOP_K = 4                # chunks passed to QA model
MIN_RELEVANCE_THRESHOLD = 0.35
DEDUPE_JACCARD_THRESHOLD = 0.7
RRF_K = 60                  # Reciprocal Rank Fusion parameter
```

### Vector Configuration
```python
DENSE_VECTOR_SIZE = 384
DENSE_MODEL = "BAAI/bge-small-en-v1.5"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
QDRANT_COLLECTION_NAME = "research_papers"
```

---

## 7. KEY FILES REFERENCE

### Chunk Creation
- **[backend/rag/retrieval/chunking/models.py](backend/rag/retrieval/chunking/models.py)** - Chunk data model
- **[backend/rag/retrieval/chunking/section_chunker.py](backend/rag/retrieval/chunking/section_chunker.py)** - Chunking algorithm
- **[backend/extraction/models/section_hierarchy.py](backend/extraction/models/section_hierarchy.py)** - Section hierarchy model
- **[backend/extraction/app/section_detector.py](backend/extraction/app/section_detector.py)** - Section detection

### Vector Store
- **[backend/rag/retrieval/indexing/qdrant_store.py](backend/rag/retrieval/indexing/qdrant_store.py)** - Collection schema & indexes
- **[backend/rag/retrieval/indexing/indexer.py](backend/rag/retrieval/indexing/indexer.py)** - Embedding & upsert logic

### Retrieval
- **[backend/rag/retrieval/pipeline.py](backend/rag/retrieval/pipeline.py)** - Top-level pipeline
- **[backend/rag/retrieval/search/hybrid_retriever.py](backend/rag/retrieval/search/hybrid_retriever.py)** - Hybrid search with filters
- **[backend/rag/retrieval/search/reranker.py](backend/rag/retrieval/search/reranker.py)** - Cross-encoder reranking

### Graph & QA
- **[backend/rag/graph.py](backend/rag/graph.py)** - LangGraph workflow, deduplication, multi-stage retrieval

### Documentation
- **[docs/RETRIEVAL_SYSTEM_FULL_REPORT_2026-03-29.md](docs/RETRIEVAL_SYSTEM_FULL_REPORT_2026-03-29.md)** - Architecture overview
- **[docs/SECTION_HIERARCHY_IMPLEMENTATION_SUMMARY.md](docs/SECTION_HIERARCHY_IMPLEMENTATION_SUMMARY.md)** - Hierarchy implementation
- **[docs/CONTENT_TYPE_CHUNKING.md](docs/CONTENT_TYPE_CHUNKING.md)** - Chunking metadata structure

---

## 8. ARCHITECTURE DIAGRAM

```
┌────────────────────────────────────────────────────────────────────┐
│  EXTRACTION PHASE                                                  │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  PDF → Docling Layout → Section Hierarchy JSON                    │
│                             ↓                                      │
│                      SectionNode tree with                         │
│                      parent_id, level, numbering                   │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                               ↓
┌────────────────────────────────────────────────────────────────────┐
│  CHUNKING PHASE                                                    │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Section + Content → SectionChunker                               │
│                        ├── TokenAwareSplitter (400 tokens)        │
│                        ├── Build section_path (titles)            │
│                        ├── Build section_path_ids (ancestry)      │
│                        └── Assign chunk_id (uuid5)                │
│                             ↓                                      │
│                      list[Chunk]  ← with hierarchy metadata       │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                               ↓
┌────────────────────────────────────────────────────────────────────┐
│  INDEXING PHASE                                                    │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Chunks → Dense Embed (384-dim BGE) + Sparse Embed (BM25)        │
│                           ↓                                        │
│                      Qdrant Collection                             │
│         ┌─────────────────────────────────────────┐               │
│         │ Vectors                Payload Indexes  │               │
│         ├─────────────────────────────────────────┤               │
│         │ dense (cosine, 384-d)  document_id      │               │
│         │ sparse (dot, BM25)     section_title    │               │
│         │                        section_path     │               │
│         │                        chunk_level      │               │
│         │                        content_type     │               │
│         │                        section_id       │               │
│         │                        parent_section_id│               │
│         │                        section_path_ids │               │
│         │                                         │               │
│         └─────────────────────────────────────────┘               │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                               ↓
┌────────────────────────────────────────────────────────────────────┐
│  RETRIEVAL PHASE                                                   │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Query + Section Filter (optional)                                │
│         ↓                                                          │
│  HybridRetriever._build_filter()                                  │
│  ├─ document_id: MatchValue                                       │
│  ├─ section_path_ids: MatchAny(["3.2"])  ← Hierarchy filter       │
│  ├─ chunk_level: MatchValue                                       │
│  └─ content_type: MatchValue                                      │
│         ↓                                                          │
│  Qdrant RRF Fusion (dense + sparse)                               │
│  ├─ Dense search (cosine on query embedding)                      │
│  ├─ Sparse search (BM25 on query)                                 │
│  └─ Merge with RRF scoring (k=60)                                │
│         ↓                                                          │
│  Top-20 candidates                                                │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                               ↓
┌────────────────────────────────────────────────────────────────────┐
│  POST-PROCESSING PHASE                                             │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  _dedupe_results()  ← Remove exact duplicates (by chunk_id)       │
│         ↓                                                          │
│  Filter references (Bibliography, References sections)            │
│         ↓                                                          │
│  Filter low scores (threshold=0.35)                               │
│         ↓                                                          │
│  _dedupe_near_identical_chunks()  ← Jaccard > 0.7                │
│         ↓                                                          │
│  FlashRank Reranking (cross-encoder)                              │
│         ↓                                                          │
│  Top-12 final results                                             │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                               ↓
┌────────────────────────────────────────────────────────────────────┐
│  QA CONTEXT                                                        │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Top-4 chunks with:                                               │
│  ├─ Full content                                                  │
│  ├─ Section context (title, numbering, level)                    │
│  ├─ Retrieval & rerank scores                                    │
│  └─ Metadata (page numbers, content_type)                        │
│         ↓                                                          │
│  Passed to LLM for answer generation                              │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 9. KEY INSIGHTS & DESIGN PATTERNS

### 9.1 Deterministic Chunk IDs
- **UUIDs are NOT random** - they use `uuid5(namespace, f"{document_id}:{chunk_index}")`
- **Benefit**: Re-indexing the same document produces identical chunk_ids → Qdrant upsert overwrites instead of creating duplicates
- **Alternative approach**: Would need timestamp-based deduplication or document versioning

### 9.2 Per-Document BM25 vs Global
- **Current design**: One BM25 encoder fitted per document, saved to disk
- **Rationale**: Simpler lifecycle management; works well when queries target specific papers
- **Trade-off**: Less optimal for multi-document collections with shared vocabulary

### 9.3 Hierarchy Filter Mechanism
- **Key insight**: `section_path_ids` is stored as an array in payload
- **Qdrant MatchAny**: Checks if any element in the payload array matches the filter value
- **Automatic descendent inclusion**: Parent "3.2" automatically includes "3.2.1", "3.2.2" without explicit expansion

### 9.4 Multi-Layer Deduplication
1. **Exact ID**: Catches identical chunks from multiple retrieval strategies
2. **Token-overlap Jaccard**: Catches near-duplicates (parent-child, summary-detail pairs)
3. **Reference filtering**: Removes bibliography/reference sections by title matching

### 9.5 Chunk Levels (Fine vs Coarse)
- **Fine chunks** (150 tokens, 30 overlap): For factual questions needing precision
- **Coarse chunks** (400 tokens, 60 overlap): For conceptual questions needing breadth
- **Both indexed together** - routing happens at query time via `chunk_level` filter

### 9.6 Reranking Strategy
- **RRF fusion** happens server-side in Qdrant (dense + sparse pre-merged)
- **Cross-encoder reranking** happens client-side (FlashRank on top-20 candidates)
- **Why two-stage**: RRF merges heterogeneous signals; cross-encoder provides fine-grained relevance

---

## 10. PERFORMANCE METRICS (From Evaluation)

From [docs/RETRIEVAL_SYSTEM_FULL_REPORT_2026-03-29.md](docs/RETRIEVAL_SYSTEM_FULL_REPORT_2026-03-29.md):

```
Retrieval Performance (32 evaluated questions):
├─ Precision@2:  0.578  (58% of top-2 results are relevant)
├─ Precision@5:  0.300  (30% of top-5 results are relevant)
├─ Recall@3:     0.906  (91% of relevant chunks present in top-3)
├─ Recall@5:     0.938  (94% of relevant chunks present in top-5)
└─ MRR:          0.815  (Mean Reciprocal Rank)

Answer Quality:
├─ Faithfulness: 0.835  (answers grounded in context)
├─ Relevancy:    0.886  (answers address questions)
└─ Context Precision: 0.448  (44% of context chunks are relevant)

Ablation Results:
├─ Dense Only:           P@3=0.39, P@5=0.26, R@5=0.83, MRR=0.72
├─ Dense + BM25:         P@3=0.41, P@5=0.26, R@5=0.83, MRR=0.77
└─ Full (Hybrid+Rerank): P@3=0.48, P@5=0.30, R@5=0.94, MRR=0.82
    └─ Improvement: +0.09 MRR vs dense-only
```

---

## 11. EXTENSION POINTS

### For hierarchical improvements:
1. **Query expansion at section level**: Expand "attention" to include section context from ancestors
2. **Multi-hop retrieval**: Start at parent section, retrieve, then drill down
3. **Relevance feedback**: Use user clicks to improve section_path_ids scoring
4. **Hierarchy-aware reranking**: Penalize results from sections far from target

### For deduplication improvements:
1. **Semantic deduplication**: Replace token-overlap with embedding similarity
2. **Configurable thresholds**: Make Jaccard threshold per-use-case
3. **Chunk provenance tracking**: Track which parent sections generated each chunk

---

This comprehensive analysis provides all necessary details for understanding and extending the hierarchical chunking RAG pipeline. All code references are production-ready and actively used in the system.
