from typing import Any


def retrieve(
    query: str,
    document_id: str | None = None,
    allowed_sections: list[str] | None = None,
) -> list[str]:
    """Retrieve context via the same RAG pipeline used by main graph flows."""
    from rag import graph as rag_graph

    pipeline = rag_graph._get_retrieval_pipeline()

    # Mirror main retrieval behavior used across the app.
    hits, _meta = rag_graph._retrieve_for_question(
        pipeline=pipeline,
        question=query,
        step_sections=allowed_sections or [],
        document_id=(document_id or "").strip(),
    )

    results: list[str] = []
    for hit in hits:
        content = str(getattr(hit, "content", "") or "").strip()
        if content:
            results.append(content)

    return results
