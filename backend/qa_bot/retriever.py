from typing import Any


def retrieve_with_metadata(
    query: str,
    document_id: str | None = None,
    allowed_sections: list[str] | None = None,
    pinned_sections: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Retrieve chunks with metadata via the main RAG pipeline."""
    from rag import graph as rag_graph

    pipeline = rag_graph._get_retrieval_pipeline()

    hits, _meta = rag_graph._retrieve_for_question(
        pipeline=pipeline,
        question=query,
        step_sections=allowed_sections or [],
        document_id=(document_id or "").strip(),
        pinned_sections=pinned_sections,
    )

    return [rag_graph._result_to_dict(hit) for hit in hits]


def retrieve(
    query: str,
    document_id: str | None = None,
    allowed_sections: list[str] | None = None,
) -> list[str]:
    """Retrieve context via the same RAG pipeline used by main graph flows."""
    results: list[str] = []
    for hit in retrieve_with_metadata(query, document_id, allowed_sections):
        content = str(hit.get("content") or "").strip()
        if content:
            results.append(content)

    return results
