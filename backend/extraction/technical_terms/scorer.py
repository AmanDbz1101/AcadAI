"""Scoring and filtering for technical-term candidates."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Set

try:
    import wordfreq  # type: ignore
except Exception:  # noqa: BLE001
    wordfreq = None


class TermScorer:
    """Score and filter candidate technical terms."""

    def __init__(self) -> None:
        self.generic_phrases = {
            "proposed method",
            "previous work",
            "et al",
            "in this paper",
            "we show",
            "results show",
            "can be",
            "is used",
            "such as",
            "based on",
            "in order",
            "this work",
            "our method",
            "our approach",
            "in this work",
            "we propose",
            "we present",
            "we use",
            "can be seen",
            "it is",
            "there are",
            "there is",
            "as well",
            "note that",
            "we note",
            "in addition",
            "as shown",
            "we can",
        }
        self.stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "this",
            "that",
            "these",
            "those",
        }

    def score_terms(
        self,
        candidates: List[Dict[str, Any]],
        text: str,
        nlp_terms: Set[str],
    ) -> List[Dict[str, Any]]:
        text_lower = text.lower()
        term_counts: Counter[str] = Counter()

        for candidate in candidates:
            term_lower = str(candidate.get("term") or "").lower()
            if term_lower:
                term_counts[term_lower] = text_lower.count(term_lower)

        max_freq = max(term_counts.values()) if term_counts else 1
        scored_terms: List[Dict[str, Any]] = []

        for candidate in candidates:
            term = str(candidate.get("term") or "").strip()
            if not term:
                continue

            term_lower = term.lower()
            if self._should_filter(term, term_lower, nlp_terms):
                continue

            term_freq_normalized = term_counts[term_lower] / max_freq
            rarity_score = self._calculate_rarity(term_lower)
            length_bonus = min(len(term.split()), 3) / 3

            final_score = (
                term_freq_normalized * 0.3 + rarity_score * 0.5 + length_bonus * 0.2
            )

            if final_score >= 0.3:
                payload = {
                    "term": term,
                    "type": candidate.get("type", "single-word"),
                    "score": round(final_score, 2),
                }
                if "expansion" in candidate:
                    payload["expansion"] = candidate["expansion"]
                scored_terms.append(payload)

        scored_terms.sort(key=lambda item: item["score"], reverse=True)
        return scored_terms

    def _calculate_rarity(self, term: str) -> float:
        if wordfreq is None:
            # Fallback rarity when wordfreq is not installed.
            if len(term.split()) > 1:
                return 0.8
            if len(term) >= 6:
                return 0.7
            return 0.5

        try:
            freq = float(wordfreq.word_frequency(term, "en"))
            return 1 - min(freq * 10000, 1.0)
        except Exception:  # noqa: BLE001
            return 0.8

    def _should_filter(self, term: str, term_lower: str, nlp_terms: Set[str]) -> bool:
        if len(term) < 2:
            return True
        if term_lower in self.stopwords:
            return True
        if term_lower in self.generic_phrases:
            return True

        words = term.split()
        if len(words) == 1 and term_lower not in nlp_terms:
            if wordfreq is None:
                return len(term_lower) <= 3
            try:
                freq = float(wordfreq.word_frequency(term_lower, "en"))
                if freq > 0.0001:
                    return True
            except Exception:  # noqa: BLE001
                return False

        return False
