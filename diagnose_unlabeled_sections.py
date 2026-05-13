#!/usr/bin/env python
"""Diagnose Unlabeled Section chunks in Qdrant index."""

import os
from pathlib import Path
from qdrant_client import QdrantClient

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "research_papers")


def main():
    print(f"Connecting to Qdrant at {QDRANT_URL}")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    print(f"Querying collection: {QDRANT_COLLECTION_NAME}")

    # Get collection info
    collection_info = client.get_collection(QDRANT_COLLECTION_NAME)
    print(f"Total points in collection: {collection_info.points_count}")

    # Search for unlabeled sections
    unlabeled_count = 0
    section_counts = {}
    page_samples = {}

    print("\nScanning for Unlabeled Section chunks...")
    try:
        scrolled, _ = client.scroll(
            collection_name=QDRANT_COLLECTION_NAME,
            limit=1000,
            with_payload=True,
        )

        for point in scrolled:
            metadata = point.payload or {}
            section_title = metadata.get("section_title", "")
            section_id = metadata.get("section_id", "")

            if section_title == "Unlabeled Section":
                unlabeled_count += 1
                page = metadata.get("page_start", "unknown")
                if page not in page_samples:
                    page_samples[page] = {
                        "chunk_id": point.id,
                        "preview": str(point.payload.get("content", ""))[:100],
                    }
            else:
                section_counts[section_title] = section_counts.get(section_title, 0) + 1

        print(f"\n✗ Found {unlabeled_count} 'Unlabeled Section' chunks")

        if page_samples:
            print("\nUnlabeled chunk samples by page:")
            for page, sample in sorted(page_samples.items()):
                print(f"  Page {page}: {sample['preview']}... (ID: {sample['chunk_id']})")

        print("\n✓ Top 10 sections by chunk count:")
        sorted_sections = sorted(section_counts.items(), key=lambda x: x[1], reverse=True)
        for section_title, count in sorted_sections[:10]:
            print(f"  {section_title}: {count} chunks")

        print(f"\nTotal sections: {len(section_counts)}")

    except Exception as e:
        print(f"Error scanning collection: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
