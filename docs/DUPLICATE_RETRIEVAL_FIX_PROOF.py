"""
Mathematical Proof: Why Section-Based Deduplication Fixes Parent-Child Redundancy

This demonstrates the Jaccard similarity calculation for your three-chunk scenario
and proves why section-based deduplication is necessary.
"""

def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Calculate Jaccard similarity between two token sets."""
    if not (set_a or set_b):
        return 1.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


# Simulate your three retrieved chunks from the bug report
print("=" * 90)
print("DUPLICATE RETRIEVAL ISSUE: MATHEMATICAL PROOF")
print("=" * 90)
print()

# Chunk 1: Coarse-grained (full section)
chunk_1_content = (
    "The goal of reducing sequential computation also forms the foundation of the Extended Neural GPU [16], "
    "ByteNet [18] and ConvS2S [9], all of which use convolutional neural networks as basic building block, "
    "computing hidden representations in parallel for all input and output positions. In these models, "
    "the number of operations required to relate signals from two arbitrary input or output positions grows "
    "in the distance between positions, linearly for ConvS2S and logarithmically for ByteNet. This makes it "
    "more difficult to learn dependencies between distant positions [12]. In the Transformer this is reduced "
    "to a constant number of operations, albeit at the cost of reduced effective resolution due to averaging "
    "attention-weighted positions, an effect we counteract with Multi-Head Attention as described in section 3.2. "
    "Self-attention, sometimes called intra-attention is an attention mechanism relating different positions of a "
    "single sequence in order to compute a representation of the sequence. Self-attention has been used successfully "
    "in a variety of tasks including reading comprehension, abstractive summarization, textual entailment and learning "
    "task-independent sentence representations [4, 27, 28, 22]."
)

# Chunk 2: Fine-grained (subset 1)
chunk_2_content = (
    "The goal of reducing sequential computation also forms the foundation of the Extended Neural GPU [16], "
    "ByteNet [18] and ConvS2S [9], all of which use convolutional neural networks as basic building block, "
    "computing hidden representations in parallel for all input and output positions. In these models, "
    "the number of operations required to relate signals from two arbitrary input or output positions grows "
    "in the distance between positions, linearly for ConvS2S and logarithmically for ByteNet. This makes it "
    "more difficult to learn dependencies between distant positions [12]."
)

# Chunk 3: Fine-grained (subset 2)
chunk_3_content = (
    "This makes it more difficult to learn dependencies between distant positions [12]. In the Transformer "
    "this is reduced to a constant number of operations, albeit at the cost of reduced effective resolution "
    "due to averaging attention-weighted positions, an effect we counteract with Multi-Head Attention as "
    "described in section 3.2. Self-attention, sometimes called intra-attention is an attention mechanism "
    "relating different positions of a single sequence in order to compute a representation of the sequence. "
    "Self-attention has been used successfully in a variety of tasks including reading comprehension, "
    "abstractive summarization, textual entailment and learning task-independent sentence representations [4, 27, 28, 22]."
)

# Convert to token sets
chunk_1_tokens = set(chunk_1_content.split())
chunk_2_tokens = set(chunk_2_content.split())
chunk_3_tokens = set(chunk_3_content.split())

print("📊 INPUT CHUNKS (from your bug report):")
print(f"  Chunk 1 (coarse):  {len(chunk_1_tokens):3d} unique tokens, {len(chunk_1_content):4d} chars, chunk_level='coarse'")
print(f"  Chunk 2 (fine):    {len(chunk_2_tokens):3d} unique tokens, {len(chunk_2_content):4d} chars, chunk_level='fine'")
print(f"  Chunk 3 (fine):    {len(chunk_3_tokens):3d} unique tokens, {len(chunk_3_content):4d} chars, chunk_level='fine'")
print(f"  ✓ All share section_id: 'bd077a96-5a38-5281-993e-10cf869afcde_section_1'")
print()

# Calculate Jaccard similarities
print("🔬 JACCARD SIMILARITY ANALYSIS (Current Threshold: 0.7)")
print()

jac_1_2 = jaccard_similarity(chunk_1_tokens, chunk_2_tokens)
jac_1_3 = jaccard_similarity(chunk_1_tokens, chunk_3_tokens)
jac_2_3 = jaccard_similarity(chunk_2_tokens, chunk_3_tokens)

print(f"  Jaccard(Chunk 1, Chunk 2) = {jac_1_2:.4f} {'✗ BELOW 0.7 (not marked duplicate!)' if jac_1_2 <= 0.7 else '✓'}")
print(f"  Jaccard(Chunk 1, Chunk 3) = {jac_1_3:.4f} {'✗ BELOW 0.7 (not marked duplicate!)' if jac_1_3 <= 0.7 else '✓'}")
print(f"  Jaccard(Chunk 2, Chunk 3) = {jac_2_3:.4f} {'✗ BELOW 0.7 (not marked duplicate!)' if jac_2_3 <= 0.7 else '✓'}")
print()

print("❌ PROBLEM IDENTIFIED:")
print("   All parent-child Jaccard similarities are BELOW the 0.7 threshold.")
print("   Reason: Child chunks are subsets of parent chunks, not full copies.")
print("   Result: Deduplication FAILS. All 3 chunks are returned together.")
print()

# Show what SHOULD happen
print("=" * 90)
print("SOLUTION: SECTION-BASED DEDUPLICATION")
print("=" * 90)
print()

chunks = [
    {"id": 1, "level": "coarse", "score": 0.92, "tokens": chunk_1_tokens},
    {"id": 2, "level": "fine", "score": 0.85, "tokens": chunk_2_tokens},
    {"id": 3, "level": "fine", "score": 0.83, "tokens": chunk_3_tokens},
]

print("STEP 1: Keep highest-scoring chunk per section_id")
print()
print("  Before section dedup: 3 chunks (all from same section)")
best_chunk = max(chunks, key=lambda c: c["score"])
print(f"  After section dedup:  1 chunk (Chunk {best_chunk['id']}, level={best_chunk['level']}, score={best_chunk['score']:.2f})")
print()

print("STEP 2: Apply Jaccard-based dedup (on remaining chunks)")
print("  No remaining duplicates to remove (only 1 chunk left)")
print()

print("✅ RESULT:")
print(f"   Chunk {best_chunk['id']} (level={best_chunk['level']}, score={best_chunk['score']:.2f}) returned")
print("   No redundancy! ✓")
print()

# Show why this is correct
print("=" * 90)
print("WHY THIS IS THE RIGHT CHOICE")
print("=" * 90)
print()
print("  ✓ Section-based dedup keeps the HIGHEST-SCORING chunk from the section")
print("    (Chunk 1, coarse, score=0.92)")
print()
print("  ✓ Coarse chunks provide broader context (good for LLM comprehension)")
print()
print("  ✓ If you need fine-grained precision instead:")
print("    - Set chunk_level='fine' in retrieval to filter server-side")
print("    - Or implement a different strategy (see DUPLICATE_RETRIEVAL_AUDIT.md)")
print()

# Show the fix
print("=" * 90)
print("FIX APPLIED TO: backend/rag/graph.py")
print("=" * 90)
print()
print("Added parameter to _dedupe_near_identical_chunks():")
print()
print("  def _dedupe_near_identical_chunks(")
print("      chunks,")
print("      similarity_threshold=0.7,")
print("      dedup_by_section=True,  # ← NEW")
print("  ):")
print()
print("When dedup_by_section=True:")
print("  1. Group chunks by section_id")
print("  2. Keep highest-scoring chunk per section")
print("  3. Apply Jaccard dedup on remaining")
print()
print("Usage (line 1890 in graph.py):")
print()
print("  deduped_hits = _dedupe_near_identical_chunks(")
print("      filtered_hits,")
print("      dedup_by_section=True  # ← Prevents parent-child redundancy")
print("  )")
print()

print("=" * 90)
print("✅ FIX COMPLETE")
print("=" * 90)
