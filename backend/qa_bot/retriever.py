from typing import Any


def retrieve_with_metadata(
    query: str,
    document_id: str | None = None,
    allowed_sections: list[str] | None = None,
) -> list[Any]:
    """Retrieve context via the same RAG pipeline used by main graph flows."""
    from rag import graph as rag_graph

    pipeline = rag_graph._get_retrieval_pipeline()

    hits, _meta = rag_graph._retrieve_for_question(
        pipeline=pipeline,
        question=query,
        step_sections=allowed_sections or [],
        document_id=(document_id or "").strip(),
        pinned_sections=pinned_sections,
    )

    results: list[Any] = []
    for hit in hits:
        if hasattr(hit, "model_dump"):
            results.append(hit.model_dump())
        elif isinstance(hit, dict):
            results.append(hit)
        else:
            results.append(
                {
                    "content": getattr(hit, "content", ""),
                    "score": getattr(hit, "score", None),
                    "metadata": getattr(hit, "metadata", {}) or {},
                }
            )

    return results
