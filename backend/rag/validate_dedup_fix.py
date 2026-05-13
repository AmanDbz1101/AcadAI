"""
Validation script for duplicate retrieval fix.

Run this to verify that section-based deduplication correctly removes
parent-child chunk redundancy from retrieval results.

Usage:
    python validate_dedup_fix.py --query "attention mechanism" --doc-id <doc_id> [--before]

Flags:
    --before : Show pre-fix behavior (section dedup disabled)
    --after  : Show post-fix behavior (section dedup enabled) [default]
"""

import json
import sys
from pathlib import Path
from typing import Any, Optional

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

try:
    from rag.graph import (
        _dedupe_near_identical_chunks,
        _result_metadata,
        _result_content,
        _result_score,
    )
except ImportError:
    print("Error: Could not import from rag.graph. Make sure you're running from the repo root.")
    sys.exit(1)


def show_dedup_comparison(
    chunks: list[Any],
    test_name: str = "Deduplication Test",
) -> None:
    """
    Compare before/after deduplication behavior.
    
    Shows:
    - Original chunk count
    - Dedup with section-based=False (old behavior)
    - Dedup with section-based=True (new behavior)
    - Detailed breakdown of removed chunks
    """
    print(f"\n{'=' * 80}")
    print(f"TEST: {test_name}")
    print(f"{'=' * 80}")
    
    print(f"\n📊 Original Chunks: {len(chunks)}")
    
    # Show original chunks
    print("\n--- Original Results ---")
    section_counts = {}
    for i, chunk in enumerate(chunks):
        meta = _result_metadata(chunk)
        score = _result_score(chunk)
        section_id = meta.get("section_id", "N/A")
        chunk_level = meta.get("chunk_level", "N/A")
        content_len = len(_result_content(chunk))
        
        section_counts.setdefault(section_id, []).append((chunk_level, score))
        
        print(f"  [{i}] section={section_id[:8]}... "
              f"level={chunk_level:6s} score={score:.4f} content_len={content_len}")
    
    # Show OLD behavior (dedup_by_section=False)
    print("\n--- Dedup (Old: section-based=False) ---")
    deduped_old = _dedupe_near_identical_chunks(chunks, dedup_by_section=False)
    print(f"  Result: {len(deduped_old)} chunks")
    for i, chunk in enumerate(deduped_old):
        meta = _result_metadata(chunk)
        score = _result_score(chunk)
        section_id = meta.get("section_id", "N/A")
        chunk_level = meta.get("chunk_level", "N/A")
        print(f"    [{i}] section={section_id[:8]}... level={chunk_level:6s} score={score:.4f}")
    
    # Show NEW behavior (dedup_by_section=True)
    print("\n--- Dedup (New: section-based=True) ---")
    deduped_new = _dedupe_near_identical_chunks(chunks, dedup_by_section=True)
    print(f"  Result: {len(deduped_new)} chunks")
    for i, chunk in enumerate(deduped_new):
        meta = _result_metadata(chunk)
        score = _result_score(chunk)
        section_id = meta.get("section_id", "N/A")
        chunk_level = meta.get("chunk_level", "N/A")
        print(f"    [{i}] section={section_id[:8]}... level={chunk_level:6s} score={score:.4f}")
    
    # Summary
    print(f"\n📈 Summary:")
    print(f"  Original:         {len(chunks):3d} chunks")
    print(f"  Old (no section): {len(deduped_old):3d} chunks (removed: {len(chunks) - len(deduped_old)})")
    print(f"  New (section):    {len(deduped_new):3d} chunks (removed: {len(chunks) - len(deduped_new)})")
    print(f"  Improvement:      Removed {len(deduped_old) - len(deduped_new)} additional redundant chunks")
    
    # Section analysis
    print(f"\n🔍 Per-Section Breakdown (Old vs New):")
    for section_id in sorted(section_counts.keys()):
        print(f"\n  Section {section_id[:16]}...")
        
        old_in_section = [c for c in deduped_old if _result_metadata(c).get("section_id") == section_id]
        new_in_section = [c for c in deduped_new if _result_metadata(c).get("section_id") == section_id]
        
        print(f"    Old (no section dedup): {len(old_in_section)} chunks")
        for c in old_in_section:
            meta = _result_metadata(c)
            print(f"      - {meta.get('chunk_level', 'N/A'):6s} (score={_result_score(c):.4f})")
        
        print(f"    New (section dedup):    {len(new_in_section)} chunks")
        for c in new_in_section:
            meta = _result_metadata(c)
            print(f"      - {meta.get('chunk_level', 'N/A'):6s} (score={_result_score(c):.4f})")
        
        if len(old_in_section) > len(new_in_section):
            removed = len(old_in_section) - len(new_in_section)
            print(f"    ✓ Removed {removed} redundant chunk(s)")


def create_test_chunks(
    base_section_id: str = "bd077a96-5a38-5281-993e-10cf869afcde_section_1",
) -> list[dict]:
    """
    Create realistic test chunks mimicking your actual retrieval results.
    
    Simulates the three-chunk scenario from your bug report:
    - 1 coarse chunk (large, full section)
    - 2 fine chunks (small, subsets of coarse)
    """
    coarse_content = (
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
        "task-independent sentence representations [4, 27, 28, 22]. End-to-end memory networks are based on a recurrent "
        "attention mechanism instead of sequence-aligned recurrence and have been shown to perform well on simple-language "
        "question answering and language modeling tasks [34]. To the best of our knowledge, however, the Transformer is the "
        "first transduction model relying entirely on self-attention to compute representations of its input and output "
        "without using sequence-aligned RNNs or convolution. In the following sections, we will describe the Transformer, "
        "motivate self-attention and discuss its advantages over models such as [17, 18] and [9]."
    )
    
    fine_content_1 = (
        "The goal of reducing sequential computation also forms the foundation of the Extended Neural GPU [16], "
        "ByteNet [18] and ConvS2S [9], all of which use convolutional neural networks as basic building block, "
        "computing hidden representations in parallel for all input and output positions. In these models, "
        "the number of operations required to relate signals from two arbitrary input or output positions grows "
        "in the distance between positions, linearly for ConvS2S and logarithmically for ByteNet. This makes it "
        "more difficult to learn dependencies between distant positions [12]."
    )
    
    fine_content_2 = (
        "This makes it more difficult to learn dependencies between distant positions [12]. In the Transformer "
        "this is reduced to a constant number of operations, albeit at the cost of reduced effective resolution "
        "due to averaging attention-weighted positions, an effect we counteract with Multi-Head Attention as "
        "described in section 3.2. Self-attention, sometimes called intra-attention is an attention mechanism "
        "relating different positions of a single sequence in order to compute a representation of the sequence. "
        "Self-attention has been used successfully in a variety of tasks including reading comprehension, "
        "abstractive summarization, textual entailment and learning task-independent sentence representations "
        "[4, 27, 28, 22]."
    )
    
    return [
        {
            "content": coarse_content,
            "score": 0.92,
            "metadata": {
                "chunk_id": "8375d6d9-7653-444a-912f-bce373af0aff",
                "point_id": "8753155a-22db-5b6f-a825-959fa533081c",
                "section_id": base_section_id,
                "chunk_level": "coarse",
                "section_title": "Attention Is All You Need",
            },
        },
        {
            "content": fine_content_1,
            "score": 0.85,
            "metadata": {
                "chunk_id": "a09a0ba8-5893-469e-a5b4-8ae4ce584e34",
                "point_id": "a00a1b27-b1d5-5a6c-ab7b-9186fc86ba6f",
                "section_id": base_section_id,
                "chunk_level": "fine",
                "section_title": "Attention Is All You Need",
            },
        },
        {
            "content": fine_content_2,
            "score": 0.83,
            "metadata": {
                "chunk_id": "e7fff3f6-11b8-42da-a83c-b8be424deb16",
                "point_id": "273e1ffa-4374-5436-acab-3be7ad55351a",
                "section_id": base_section_id,
                "chunk_level": "fine",
                "section_title": "Attention Is All You Need",
            },
        },
    ]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Validate duplicate retrieval fix (section-based deduplication)"
    )
    parser.add_argument(
        "--test",
        choices=["default", "multi_section"],
        default="default",
        help="Which test scenario to run",
    )
    
    args = parser.parse_args()
    
    # Run test
    if args.test == "default":
        print("\n🧪 Running Default Test: Single Section with Coarse+Fine Chunks")
        print("    This replicates your reported issue:")
        print("    - 1 coarse chunk (full section content)")
        print("    - 2 fine chunks (subsets of coarse)")
        print("    - All from the same section_id")
        
        test_chunks = create_test_chunks()
        show_dedup_comparison(test_chunks, "Single Section (Coarse + 2 Fine)")
    
    elif args.test == "multi_section":
        print("\n🧪 Running Multi-Section Test")
        print("    Tests deduplication across multiple sections")
        
        test_chunks = (
            create_test_chunks(base_section_id="section_1")
            + create_test_chunks(base_section_id="section_2")
        )
        show_dedup_comparison(test_chunks, "Multiple Sections")
    
    print("\n" + "=" * 80)
    print("✅ Validation complete!")
    print("=" * 80)
