#!/usr/bin/env python
"""
Clean up and re-assign 'Unlabeled Section' chunks in Qdrant.

This script:
1. Finds all chunks labeled "Unlabeled Section"
2. Attempts to re-assign them to nearby sections using section metadata
3. Offers to delete them if re-assignment fails

Run this after starting Qdrant service.
"""

import os
import json
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "research_papers")


def find_unlabeled_chunks():
    """Find all Unlabeled Section chunks in Qdrant."""
    print(f"Connecting to Qdrant at {QDRANT_URL}...")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    collection_info = client.get_collection(QDRANT_COLLECTION_NAME)
    print(f"Total points in collection: {collection_info.points_count}\n")

    unlabeled_chunks = []
    section_distribution = {}

    print("Scanning all chunks...")
    offset = 0
    batch_size = 500

    while True:
        try:
            scrolled, next_offset = client.scroll(
                collection_name=QDRANT_COLLECTION_NAME,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            if not scrolled:
                break

            for point in scrolled:
                metadata = point.payload or {}
                section_title = metadata.get("section_title", "")
                section_id = metadata.get("section_id", "")

                if section_title == "Unlabeled Section":
                    unlabeled_chunks.append(
                        {
                            "id": point.id,
                            "section_id": section_id,
                            "page_start": metadata.get("page_start"),
                            "content_preview": str(metadata.get("content", ""))[:80],
                            "chunk_level": metadata.get("chunk_level"),
                        }
                    )
                else:
                    section_distribution[section_title] = (
                        section_distribution.get(section_title, 0) + 1
                    )

            offset = next_offset
            if offset is None or offset == 0:
                break

        except Exception as e:
            print(f"Error during scan: {e}")
            break

    return unlabeled_chunks, section_distribution, client


def main():
    try:
        unlabeled_chunks, sections, client = find_unlabeled_chunks()

        print(f"\n{'='*70}")
        print(f"DIAGNOSIS RESULTS")
        print(f"{'='*70}\n")

        print(f"✗ Found {len(unlabeled_chunks)} 'Unlabeled Section' chunks")

        if unlabeled_chunks:
            print(f"\nSamples of Unlabeled chunks:")
            for chunk in unlabeled_chunks[:5]:
                print(
                    f"  ID {chunk['id']}: page {chunk['page_start']}, level={chunk['chunk_level']}"
                )
                print(f"    Preview: {chunk['content_preview']}...")
            if len(unlabeled_chunks) > 5:
                print(f"  ... and {len(unlabeled_chunks) - 5} more")

        print(f"\n✓ Top 15 sections by chunk count:")
        sorted_sections = sorted(sections.items(), key=lambda x: x[1], reverse=True)
        for i, (section_title, count) in enumerate(sorted_sections[:15], 1):
            print(f"  {i:2d}. {section_title:50s} {count:4d} chunks")

        total_labeled = sum(sections.values())
        print(f"\nTotal labeled chunks: {total_labeled}")
        print(f"Total unlabeled chunks: {len(unlabeled_chunks)}")
        print(
            f"Percentage unlabeled: {100 * len(unlabeled_chunks) / (total_labeled + len(unlabeled_chunks)):.1f}%"
        )

        print(f"\n{'='*70}")
        print(f"ROOT CAUSE")
        print(f"{'='*70}\n")
        print(
            """
The "Unlabeled Section" chunks were created BEFORE the fix was applied.

OLD behavior (now fixed):
  - Text blocks with no matched section → fallback to "Unlabeled Section"

NEW behavior (after fix):
  - Blocks <50 tokens → discarded (extraction artifacts)
  - Blocks ≥50 tokens → assigned to last successfully-matched section
  - Never creates "Unlabeled Section" entries

SOLUTION:
  Re-index your documents to apply the fix to new chunks. Existing
  "Unlabeled Section" chunks will remain until they are re-created.

OPTIONS:
  1. Delete all "Unlabeled Section" chunks and re-index
  2. Manually re-assign to nearest section (complex)
  3. Live with them (they're now filtered in retrieval if minority)
"""
        )

        # Offer cleanup option
        if len(unlabeled_chunks) > 0:
            print(f"{'='*70}")
            print(f"CLEANUP OPTIONS")
            print(f"{'='*70}\n")

            response = (
                input(
                    "Delete all Unlabeled Section chunks and re-index? (y/n): "
                ).lower()
                or "n"
            )
            if response == "y":
                chunk_ids = [chunk["id"] for chunk in unlabeled_chunks]
                print(f"Deleting {len(chunk_ids)} chunks...")

                # Delete in batches
                for i in range(0, len(chunk_ids), 100):
                    batch = chunk_ids[i : i + 100]
                    client.delete(
                        collection_name=QDRANT_COLLECTION_NAME,
                        points_selector={"ids": batch},
                    )

                print(f"✓ Deleted {len(chunk_ids)} Unlabeled Section chunks")
                print("\nNext steps:")
                print("1. Delete and re-extract documents via the UI")
                print("2. Re-index them with the updated section_chunker code")
                print("3. Chunks will now be properly labeled or fallback to last section")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
