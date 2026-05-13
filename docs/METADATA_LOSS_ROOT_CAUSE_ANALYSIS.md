# Metadata Loss Investigation: RAG System Retrieval

## Problem Statement
Qdrant retrieval returns 20 chunks with only `chunk_id` and `text`, missing metadata fields like:
- `section_title`
- `page_start`/`page_end`
- `section_path`
- `section_level`
- `content_type`

## Complete Metadata Flow Analysis

### Stage 1: Chunk Creation (✅ CORRECT)
**File**: `backend/rag/retrieval/chunking/section_chunker.py` (line 1109-1127)

```python
chunks.append(
    Chunk(
        document_id=document_id,
        content=window,
        content_type="text",
        token_count=splitter.count_tokens(window),
        chunk_index=chunk_index,
        chunk_level=chunk_level,
        section_id=section_id,
        section_title=node.get("title", ""),        # ✓ Set
        section_level=node.get("level", 1),         # ✓ Set
        section_numbering=node.get("numbering"),    # ✓ Set
        section_path=section_path,                  # ✓ Set
        section_path_ids=section_path_ids,          # ✓ Set
        parent_section_id=node.get("parent_id"),    # ✓ Set
        page_start=node.get("page_start"),          # ✓ Set
        page_end=node.get("page_end"),              # ✓ Set
        element_ids=element_ids,
        source_file=source_file_name,
    )
)
```

**Chunk Model** (`backend/rag/retrieval/chunking/models.py` line 91-147):
- Has `to_payload()` method that converts all fields to a flat dict
- Payload includes all metadata fields

---

### Stage 2: Storage to Qdrant (✅ CORRECT)
**File**: `backend/rag/retrieval/indexing/indexer.py` (line 279-300)

```python
payload = chunks[i].to_payload()  # Line 279 - Converts Chunk to dict
logger.debug(
    "Chunk payload section_path: %s section_title: %s",
    payload.get("section_path"),      # ✓ Present in payload
    payload.get("section_title"),     # ✓ Present in payload
)
points.append(
    PointStruct(
        id=chunk_uuid,
        payload=payload,               # ✓ Full payload stored
        vector={...}
    )
)
client.upsert(
    collection_name=collection,
    points=points,
    wait=True,
)
```

**Verification**: Debug logs show payload contains section_path and section_title before upsert.

---

### Stage 3: Vector Store Initialization (✓ NORMAL)
**File**: `backend/rag/retrieval/indexing/qdrant_store.py` (line 322-349)

```python
def get_vector_store(self, dense_encoder, sparse_encoder):
    from langchain_qdrant import QdrantVectorStore, RetrievalMode
    
    return QdrantVectorStore(
        client=self.client,
        collection_name=self.collection_name,
        embedding=dense_encoder,
        sparse_embedding=sparse_encoder,
        retrieval_mode=RetrievalMode.HYBRID,
        vector_name=DENSE_VECTOR_NAME,
        sparse_vector_name=SPARSE_VECTOR_NAME,
        content_payload_key="content",  # Maps "content" field as page_content
    )
```

**Note**: No `with_payload` parameter specified, so LangChain's default behavior applies.
- LangChain's QdrantVectorStore may NOT return all payload fields by default
- Returns only fields needed for the document object

---

### Stage 4: Retrieval Query (⚠️ SUSPICIOUS)
**File**: `backend/rag/retrieval/search/hybrid_retriever.py` (line 195-225)

#### Path 1: Hybrid Search
```python
def _hybrid_search(self, query: str, payload_filter):
    vs = self._get_vector_store()
    fusion_query = self._build_hybrid_fusion_query()
    
    try:
        return vs.similarity_search_with_score(
            query,
            k=self.top_k,
            filter=payload_filter,
            hybrid_fusion=fusion_query,
        )  # ⚠️ NO with_payload=True parameter!
    except TypeError:
        return vs.similarity_search_with_score(
            query,
            k=self.top_k,
            filter=payload_filter,
        )
```

#### Path 2: Dense Fallback
```python
def _dense_search(self, query: str, payload_filter):
    vs = self._get_vector_store()
    return vs.similarity_search_with_score(
        query,
        k=self.top_k,
        filter=payload_filter,
    )  # ⚠️ NO with_payload=True parameter!
```

**Problem**: Both `similarity_search_with_score()` calls **DO NOT explicitly request payloads**.

---

### Stage 5: Result Processing (⚠️ WORKAROUND ATTEMPTED BUT FAILING)
**File**: `backend/rag/retrieval/search/hybrid_retriever.py` (line 152-168)

```python
for doc, score in hits:
    meta = dict(doc.metadata) if doc.metadata else {}
    
    # Attempt to enrich with full Qdrant payload
    qdrant_payload = self._get_full_qdrant_payload(doc)  # Line 153
    if qdrant_payload:
        meta = {**meta, **qdrant_payload}
    
    results.append(
        RetrievalResult(
            content=doc.page_content,
            score=float(score),
            metadata=meta,
        )
    )
```

#### The `_get_full_qdrant_payload()` Method (line 366-417)
```python
def _get_full_qdrant_payload(self, doc) -> dict | None:
    """
    LangChain's QdrantVectorStore may not surface all payload fields;
    this method queries Qdrant directly to get the complete payload.
    """
    try:
        metadata = doc.metadata if isinstance(getattr(doc, "metadata", None), dict) else {}
        chunk_id = metadata.get("chunk_id")
        document_id = metadata.get("document_id")
        
        if not chunk_id:
            return None  # ⚠️ FAILS if chunk_id not in doc.metadata!
        
        vs = self._get_vector_store()
        client = vs.client
        collection_name = vs.collection_name
        
        scroll_filter = Filter(
            must=[
                FieldCondition(key="chunk_id", match=MatchValue(value=chunk_id)),
            ]
            + (
                [FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                if document_id
                else []
            )
        )
        
        points, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=scroll_filter,
            limit=1,
            with_payload=True,           # ✓ Explicitly requests payload
            with_vectors=False,
        )
        if not points:
            return None
        
        payload = points[0].payload if hasattr(points[0], "payload") else None
        return dict(payload) if payload else None
    except Exception as exc:
        logger.debug("HybridRetriever: failed to fetch full payload: %s", exc)
        return None  # ⚠️ SILENT FAILURE - no metadata returned!
```

**Critical Issues**:
1. **Line 375**: Returns `None` if `chunk_id` is missing from `doc.metadata`
   - If LangChain's doc doesn't include chunk_id, the fallback fails completely
2. **Exception Handling**: Catches all exceptions and returns None silently (line 415-416)
   - Any Qdrant connection issue, network error, or other problem is silently swallowed
   - User gets back metadata-less results with no warning

---

## Diagnosis: Three Possible Failure Points

### Possibility A: LangChain's QdrantVectorStore Not Returning Basic Metadata
**Symptom**: `doc.metadata` is empty or missing `chunk_id`, `document_id`

**Impact**: `_get_full_qdrant_payload()` fails at line 375 (no chunk_id)

**Solution**: Explicitly pass `with_payload=True` to `similarity_search_with_score()`

---

### Possibility B: `_get_full_qdrant_payload()` Exception Silently Fails
**Symptom**: Qdrant client.scroll() throws an exception

**Possible Causes**:
- Qdrant service temporarily unavailable
- Network connectivity issue
- Client not properly initialized
- Collection mismatch

**Impact**: Exception caught at line 415, returns None silently

**Solution**: Add logging before exception catch to diagnose root cause

---

### Possibility C: Metadata Fields Not in Qdrant Payload
**Symptom**: `section_title`, `page_start`, `page_end` not written to Qdrant during indexing

**Impact**: Even if payload is fetched, fields are missing

**Solution**: Verify indexer logs show fields being written to payload (debug logs at line 281-284)

---

## Current Workaround Status

**What the code attempts**:
1. Get metadata from LangChain doc.metadata
2. Query Qdrant directly for full payload as fallback
3. Merge both sources

**Why it's failing**:
1. LangChain may not return minimal metadata (chunk_id, document_id)
2. Fallback query fails silently if either condition above is true
3. User gets back only what LangChain's doc provides (chunk_id, text)

---

## Recommended Fix (Priority Order)

### Fix 1 (HIGH PRIORITY): Explicit with_payload=True
**File**: `backend/rag/retrieval/search/hybrid_retriever.py` lines 195-225

```python
def _hybrid_search(self, query: str, payload_filter):
    vs = self._get_vector_store()
    fusion_query = self._build_hybrid_fusion_query()
    
    try:
        return vs.similarity_search_with_score(
            query,
            k=self.top_k,
            filter=payload_filter,
            hybrid_fusion=fusion_query,
            with_payload=True,  # ← ADD THIS
        )
    except TypeError:
        return vs.similarity_search_with_score(
            query,
            k=self.top_k,
            filter=payload_filter,
            with_payload=True,  # ← ADD THIS
        )

def _dense_search(self, query: str, payload_filter):
    vs = self._get_vector_store()
    return vs.similarity_search_with_score(
        query,
        k=self.top_k,
        filter=payload_filter,
        with_payload=True,  # ← ADD THIS
    )
```

**Rationale**: Ensures LangChain requests payloads from Qdrant in the similarity search

---

### Fix 2 (MEDIUM PRIORITY): Add Debugging to Fallback
**File**: `backend/rag/retrieval/search/hybrid_retriever.py` line 415

```python
except Exception as exc:
    logger.warning(  # ← Changed from debug to warning
        "HybridRetriever: failed to fetch full qdrant payload for chunk_id=%s: %s",
        chunk_id,
        exc,
    )
    return None
```

**Rationale**: Helps diagnose when fallback fails

---

### Fix 3 (LOW PRIORITY): Verify Indexer Payload
**File**: `backend/rag/retrieval/indexing/indexer.py` line 281

Check logs after next indexing run to confirm:
```
Chunk payload section_path: [...] section_title: [Title Name]
```

If logs show missing section_title, the issue is in chunking, not retrieval.

---

## Testing Recommendation

After applying fixes:

1. **Test 1**: Index a new document and grep indexer logs for payload debug messages
   - Verify section_title, page_start are logged
   
2. **Test 2**: Query Qdrant directly to verify payload:
   ```bash
   python -c "
   from qdrant_client import QdrantClient
   client = QdrantClient(':memory:')
   # Query collection, check with_payload=True results
   "
   ```

3. **Test 3**: Run retrieval and verify metadata in RetrievalResult objects
   - Should show section_title, page_start, page_end in metadata dict

4. **Test 4**: Verify chat API response includes sources with section metadata
   - Check that section_title appears in sources array in API response

---

## Expected Outcome After Fix

**Before**:
```json
{
  "content": "...",
  "chunk_id": "...",
  "text": "..."
}
```

**After**:
```json
{
  "chunk_id": "...",
  "document_id": "...",
  "content": "...",
  "content_type": "text",
  "section_title": "Methods",
  "section_level": 2,
  "section_path": ["Introduction", "Background", "Methods"],
  "page_start": 5,
  "page_end": 12,
  "token_count": 256,
  "source_file": "paper.pdf"
}
```

---

## Likely Root Cause

**Most probable**: LangChain's `similarity_search_with_score()` without `with_payload=True` parameter returns Document objects with minimal metadata (only what's needed for content and minimal tracking), and the fallback `_get_full_qdrant_payload()` fails silently when it can't extract `chunk_id` from the minimal metadata provided.

**Solution**: Add `with_payload=True` to all `similarity_search_with_score()` calls to ensure LangChain requests complete payloads from Qdrant.
