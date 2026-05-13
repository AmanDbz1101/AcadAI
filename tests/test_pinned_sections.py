from langchain_core.messages import HumanMessage

from backend.qa_bot.nodes import chat_node
from backend.rag import graph as rag_graph


class _DummyPipeline:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("section_path_any"):
            return [
                {
                    "content": "Scoped hit",
                    "score": 0.5,
                    "metadata": {
                        "chunk_id": f"scoped-{len(self.calls)}",
                        "section_title": "Introduction",
                        "section_path": ["Introduction"],
                    },
                }
            ]
        return [
            {
                "content": "Fallback hit",
                "score": 0.4,
                "metadata": {
                    "chunk_id": f"fallback-{len(self.calls)}",
                    "section_title": "Methods",
                    "section_path": ["Methods"],
                },
            }
        ]

    def rerank_results(self, query, results, top_n):
        return results


def test_hard_scoped_retrieval_skips_fallback() -> None:
    pipeline = _DummyPipeline()

    rag_graph._retrieve_for_question(
        pipeline=pipeline,
        question="What is the method?",
        step_sections=["Introduction"],
        document_id="",
        pinned_sections=["Introduction"],
    )

    assert len(pipeline.calls) == 1
    assert pipeline.calls[0].get("section_path_any")


def test_unconstrained_retrieval_still_falls_back() -> None:
    pipeline = _DummyPipeline()

    rag_graph._retrieve_for_question(
        pipeline=pipeline,
        question="What is the method?",
        step_sections=["Introduction"],
        document_id="",
        pinned_sections=None,
    )

    assert any(call.get("section_path_any") is None for call in pipeline.calls)


def test_pinned_sections_returns_not_found_message(monkeypatch) -> None:
    def _fake_retrieve(*_args, **_kwargs):
        return [
            {
                "content": "Other section content",
                "metadata": {"section_title": "Methods"},
            }
        ]

    monkeypatch.setattr("backend.qa_bot.nodes.retrieve_with_metadata", _fake_retrieve)

    state = {
        "messages": [HumanMessage(content="What is the method?")],
        "allowed_sections": [],
        "pinned_sections": ["Introduction"],
        "document_id": "",
    }

    result = chat_node(state)

    assert result.get("found_in_scope") is False
    assert result.get("retrieved_chunks") == []
    assert result["messages"][0].content.startswith("The selected section(s)")
