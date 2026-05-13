from rag.retrieval.chunking import section_chunker


def test_unresolved_blocks_fallback_to_last_section() -> None:
    sections = [
        {
            "section_id": "1",
            "title": "Introduction",
            "reading_order": 1,
        }
    ]
    long_intro = "intro " * 60
    long_fallback = "fallback " * 60

    elements = {
        "text_blocks": [
            {
                "text": "Introduction",
                "label": "section_header",
                "page": 1,
                "reading_order": 1,
            },
            {
                "text": long_intro,
                "label": "paragraph",
                "page": 1,
                "reading_order": 2,
            },
            {
                "text": "Unknown Heading",
                "label": "section_header",
                "page": 1,
                "reading_order": 3,
            },
            {
                "text": long_fallback,
                "label": "paragraph",
                "page": 1,
                "reading_order": 4,
            },
        ]
    }

    section_texts, assignments, unresolved = section_chunker._map_section_texts_from_nearest_headings(
        elements,
        sections,
    )

    assert "1" in section_texts
    assert long_intro.strip() in section_texts["1"]
    assert long_fallback.strip() in section_texts["1"]
    assert unresolved == []
    assert any(a.get("section_id") == "1" for a in assignments)


def test_short_unresolved_blocks_are_discarded() -> None:
    sections = [
        {
            "section_id": "1",
            "title": "Introduction",
            "reading_order": 1,
        }
    ]
    short_text = "short " * 10
    unresolved_blocks = [
        {
            "text": short_text,
            "label": "paragraph",
            "section_id": "1",
        }
    ]

    section_texts, assignments = section_chunker._map_unresolved_blocks_from_element_tags(
        unresolved_blocks,
        sections,
    )

    assert section_texts == {}
    assert assignments == []
