"""
FlashRank cross-encoder reranker.

Takes a list of :class:`~rag.states.RetrievalResult` objects retrieved by
:class:`HybridRetriever`, scores them with a local cross-encoder, and
returns the top-N re-sorted results.

Model: ``ms-marco-MiniLM-L-12-v2`` (small, fast, no API key required).

Why FlashRank?
--------------
* Pure-Python, no separate server required.
* Pre-quantised ONNX models for CPU-fast inference.
* ``flashrank.Ranker`` accepts ``(query, passages)`` and returns ranked hits.
"""

from __future__ import annotations

import logging
from typing import Optional

from rag.retrieval.config import RERANKER_MODEL, RERANKER_TOP_N

logger = logging.getLogger(__name__)


class FlashRankReranker:
    """
    Rerank retrieval candidates using a local FlashRank cross-encoder.

    Parameters
    ----------
    model_name : str
        FlashRank model identifier (default ``ms-marco-MiniLM-L-12-v2``).
    top_n : int
        Number of results to keep after reranking (default 5).
    """

    def __init__(
        self,
        model_name: str = RERANKER_MODEL,
        top_n: int = RERANKER_TOP_N,
    ) -> None:
        self.model_name = model_name
        self.top_n = top_n
        self._ranker = None  # lazy

    # ── Lazy init ─────────────────────────────────────────────────────────────

    def _load(self):
        if self._ranker is not None:
            return self._ranker
        try:
            from flashrank import Ranker  # type: ignore

            self._ranker = Ranker(model_name=self.model_name, cache_dir="/tmp/flashrank")
            logger.info("FlashRankReranker: loaded model %s", self.model_name)
        except ImportError:
            logger.error(
                "FlashRankReranker: 'flashrank' is not installed. "
                "Run: pip install flashrank"
            )
            raise
        return self._ranker

    # ── Main API ──────────────────────────────────────────────────────────────

    def rerank(self, query: str, results: list) -> list:
        """
        Rerank *results* for *query* and return the top-N.

        Parameters
        ----------
        query : str
            The search query.
        results : list[RetrievalResult]
            Candidates from the hybrid retriever.

        Returns
        -------
        list[RetrievalResult]
            Up to ``top_n`` results, sorted by cross-encoder score descending.
            Each result's ``metadata`` dict gains a ``"rerank_score"`` key and
            the original ``"retrieval_score"`` is preserved.
        """
        from rag.states import RetrievalResult  # local to avoid circular import
        from flashrank import RerankRequest  # type: ignore

        if not results:
            return results

        ranker = self._load()

        # Build passages for FlashRank
        passages = [
            {"id": i, "text": r.content, "meta": r.metadata}
            for i, r in enumerate(results)
        ]

        request = RerankRequest(query=query, passages=passages)
        ranked = ranker.rerank(request)

        # Map back to RetrievalResult; limit to top_n
        reranked: list = []
        for hit in ranked[: self.top_n]:
            original = results[hit["id"]]
            new_meta = dict(original.metadata)
            new_meta["rerank_score"] = float(hit["score"])
            new_meta["retrieval_score"] = original.score  # preserve original score
            reranked.append(
                RetrievalResult(
                    content=original.content,
                    score=float(hit["score"]),  # rerank score becomes primary score
                    metadata=new_meta,
                )
            )

        logger.info(
            "FlashRankReranker: reranked %d → %d results for query '%s'",
            len(results),
            len(reranked),
            query[:60],
        )
        return reranked
