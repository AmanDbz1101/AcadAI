"""Tests for retrieval tuning knobs: top_k, rrf_k, and relevance threshold."""

from __future__ import annotations

import importlib
from importlib import import_module
from dataclasses import dataclass

import pytest

from backend.rag.retrieval.pipeline import RetrievalPipeline
from backend.rag.retrieval.search.hybrid_retriever import HybridRetriever


class _DummyStoreManager:
    def __init__(self, vector_store) -> None:
        self._vector_store = vector_store

    def get_vector_store(self, dense_encoder, sparse_encoder):
        return self._vector_store


class _RecordingVectorStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def similarity_search_with_score(self, query, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return []


@dataclass
class _FakeResult:
    content: str
    score: float
    metadata: dict


def test_hybrid_retriever_passes_top_k_to_vector_store() -> None:
    """top_k on HybridRetriever should control k passed to Qdrant search."""
    vector_store = _RecordingVectorStore()
    retriever = HybridRetriever(
        store_manager=_DummyStoreManager(vector_store),
        dense_encoder=object(),
        sparse_encoder=object(),
        top_k=9,
    )

    retriever._hybrid_search("attention", payload_filter=None)

    assert len(vector_store.calls) == 1
    assert vector_store.calls[0]["k"] == 9


def test_hybrid_retriever_builds_rrf_fusion_query() -> None:
    """Retriever should always build an RRF fusion query object."""
    retriever = HybridRetriever(
        store_manager=_DummyStoreManager(_RecordingVectorStore()),
        dense_encoder=object(),
        sparse_encoder=object(),
        rrf_k=77,
    )

    fusion_query = retriever._build_hybrid_fusion_query()

    assert hasattr(fusion_query, "fusion")
    # In some qdrant-client versions this is an enum (default RRF), in others
    # it may carry an RRF object with k.
    fusion_value = fusion_query.fusion
    assert "rrf" in str(fusion_value).lower()


def test_pipeline_propagates_top_k_and_top_n(monkeypatch: pytest.MonkeyPatch) -> None:
    """query(top_k, top_n) should pass values to retriever init and reranker stage."""
    backend_hybrid_module = import_module("backend.rag.retrieval.search.hybrid_retriever")
    rag_hybrid_module = import_module("rag.retrieval.search.hybrid_retriever")

    captured: dict[str, int] = {}

    class FakeHybridRetriever:
        def __init__(
            self,
            store_manager,
            dense_encoder,
            sparse_encoder,
            top_k,
            rrf_k=None,
        ) -> None:
            captured["top_k"] = top_k

        def retrieve(self, **kwargs):
            return [
                _FakeResult(content=f"chunk-{i}", score=1.0 - (i * 0.1), metadata={})
                for i in range(6)
            ]

    monkeypatch.setattr(backend_hybrid_module, "HybridRetriever", FakeHybridRetriever)
    monkeypatch.setattr(rag_hybrid_module, "HybridRetriever", FakeHybridRetriever)

    pipeline = RetrievalPipeline(enable_reranking=False)
    monkeypatch.setattr(pipeline, "_get_store_manager", lambda: object())
    monkeypatch.setattr(pipeline, "_get_dense_encoder", lambda: object())
    monkeypatch.setattr(pipeline, "_get_sparse_encoder", lambda document_id: object())

    def _fake_rerank(query: str, results: list, top_n: int):
        captured["top_n"] = top_n
        return results[:top_n]

    monkeypatch.setattr(pipeline, "rerank_results", _fake_rerank)

    results = pipeline.query(
        query="what is transformer",
        document_id="doc-1",
        top_k=11,
        top_n=3,
        rerank=True,
    )

    assert captured["top_k"] == 11
    assert captured["top_n"] == 3
    assert len(results) == 3


def test_min_relevance_threshold_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """MIN_RELEVANCE_THRESHOLD should be tunable via environment variable."""
    import config as root_config

    monkeypatch.setenv("MIN_RELEVANCE_THRESHOLD", "0.62")
    importlib.reload(root_config)
    assert root_config.MIN_RELEVANCE_THRESHOLD == pytest.approx(0.62)

    monkeypatch.delenv("MIN_RELEVANCE_THRESHOLD", raising=False)
    importlib.reload(root_config)
    assert root_config.MIN_RELEVANCE_THRESHOLD == pytest.approx(0.35)


def test_query_trace_payload_includes_chunk_previews(monkeypatch: pytest.MonkeyPatch) -> None:
    """LangSmith trace payload should include candidate and returned chunk previews."""
    pipeline_module = import_module("backend.rag.retrieval.pipeline")
    backend_hybrid_module = import_module("backend.rag.retrieval.search.hybrid_retriever")
    rag_hybrid_module = import_module("rag.retrieval.search.hybrid_retriever")

    class FakeHybridRetriever:
        def __init__(self, store_manager, dense_encoder, sparse_encoder, top_k, rrf_k=None) -> None:
            pass

        def retrieve(self, **kwargs):
            return [
                _FakeResult(
                    content="Transformer uses multi-head attention for representation learning.",
                    score=0.91,
                    metadata={"_id": "chunk-1", "section_title": "Attention"},
                ),
                _FakeResult(
                    content="Residual connections stabilize deep architectures.",
                    score=0.67,
                    metadata={"_id": "chunk-2", "section_title": "Architecture"},
                ),
            ]

    monkeypatch.setattr(backend_hybrid_module, "HybridRetriever", FakeHybridRetriever)
    monkeypatch.setattr(rag_hybrid_module, "HybridRetriever", FakeHybridRetriever)

    captured_stages: list[tuple[str, dict]] = []

    def _fake_trace(stage: str, payload: dict):
        captured_stages.append((stage, payload))
        return {"stage": stage, **payload}

    monkeypatch.setattr(pipeline_module, "_trace_retrieval_stage", _fake_trace)

    pipeline = RetrievalPipeline(enable_reranking=False)
    monkeypatch.setattr(pipeline, "_get_store_manager", lambda: object())
    monkeypatch.setattr(pipeline, "_get_dense_encoder", lambda: object())
    monkeypatch.setattr(pipeline, "_get_sparse_encoder", lambda document_id: object())

    results = pipeline.query(
        query="how does attention work",
        document_id="doc-1",
        top_k=5,
        top_n=2,
        rerank=False,
    )

    assert len(results) == 2

    candidate_payload = next(payload for stage, payload in captured_stages if stage == "candidate_retrieval")
    final_payload = next(payload for stage, payload in captured_stages if stage == "final_output")

    assert "candidate_chunks" in candidate_payload
    assert candidate_payload["candidate_chunks"]
    assert candidate_payload["candidate_chunks"][0]["chunk_id"] == "chunk-1"
    assert "content_preview" in candidate_payload["candidate_chunks"][0]

    assert "returned_chunks" in final_payload
    assert len(final_payload["returned_chunks"]) == 2
    assert final_payload["returned_chunks"][0]["section_title"] == "Attention"
