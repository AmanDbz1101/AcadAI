from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from backend.api.app import app, _require_auth_user_id, _make_store
from backend.qa_bot.graph import graph as qa_graph


class _StubStore:
    def user_has_access_to_paper(self, user_id: int, paper_id: int) -> bool:
        return True

    def get_paper_by_id(self, paper_id: int):
        return {"id": paper_id, "document_uuid": "doc-1"}


def test_chat_response_includes_sources_and_scoped(monkeypatch):
    monkeypatch.setattr("backend.api.app._require_auth_user_id", lambda _auth: 1)
    monkeypatch.setattr("backend.api.app._make_store", lambda: _StubStore())

    def _fake_invoke(_state):
        return {
            "messages": [AIMessage(content="Answer text")],
            "retrieved_chunks": [
                {
                    "content": "x" * 200,
                    "metadata": {"section_title": "Introduction", "page_start": 3},
                }
            ],
        }

    monkeypatch.setattr(qa_graph, "invoke", _fake_invoke)

    client = TestClient(app)
    payload = {
        "messages": [{"role": "user", "content": "Hi"}],
        "allowed_sections": ["Introduction"],
    }
    response = client.post("/api/papers/1/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["assistant_message"] == "Answer text"
    assert data["scoped"] is True
    assert data["sources"][0]["section_title"] == "Introduction"
    assert data["sources"][0]["page"] == 3
    assert data["sources"][0]["content_preview"] == "x" * 120
