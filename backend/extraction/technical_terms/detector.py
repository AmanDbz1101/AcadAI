"""Core technical-term detection pipeline with graceful fallbacks."""

from __future__ import annotations

import re
import warnings
from typing import Any, Dict, List, Optional, Set, Tuple

from .acronym_extractor import AcronymExtractor
from .scorer import TermScorer

try:
    import spacy
    from spacy.matcher import Matcher
except Exception:  # noqa: BLE001
    spacy = None
    Matcher = None  # type: ignore


class TechnicalTermDetector:
    """Detect technical terms from scientific text."""

    def __init__(self) -> None:
        self.acronym_extractor = AcronymExtractor()
        self.scorer = TermScorer()
        self.nlp = self._load_spacy_model()
        self.matcher = self._setup_matcher() if self.nlp is not None else None

    def _load_spacy_model(self):
        if spacy is None:
            return None
        try:
            return spacy.load("en_core_sci_lg")
        except OSError:
            warnings.warn(
                "SciSpaCy model 'en_core_sci_lg' not found; falling back to en_core_web_sm."
            )
            try:
                return spacy.load("en_core_web_sm")
            except OSError:
                warnings.warn("No spaCy model found; using regex-only technical-term detection.")
                return None

    def _setup_matcher(self):
        matcher = Matcher(self.nlp.vocab)
        matcher.add("ADJ_NOUN", [[{"POS": "ADJ"}, {"POS": "NOUN"}]])
        matcher.add("NOUN_NOUN", [[{"POS": "NOUN"}, {"POS": "NOUN"}]])
        matcher.add(
            "NOUN_NOUN_NOUN",
            [[{"POS": "NOUN"}, {"POS": "NOUN"}, {"POS": "NOUN"}]],
        )
        matcher.add(
            "NOUN_OF_NOUN",
            [[{"POS": "NOUN"}, {"LOWER": "of"}, {"POS": "NOUN"}]],
        )
        matcher.add(
            "ADJ_ADJ_NOUN",
            [[{"POS": "ADJ"}, {"POS": "ADJ"}, {"POS": "NOUN"}]],
        )
        return matcher

    def detect(self, text: str) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []

        acronyms = self.acronym_extractor.extract_acronyms(text)

        if self.nlp is None or self.matcher is None:
            regex_candidates = self._extract_regex_candidates(text)
            merged = self._merge_candidates(acronyms, [], [], regex_candidates)
            return self.scorer.score_terms(merged, text, set())

        doc = self.nlp(text)
        nlp_terms = self._extract_ner_terms(doc)
        noun_chunks = self._extract_noun_chunks(doc)
        pattern_matches = self._extract_pattern_matches(doc)

        merged = self._merge_candidates(acronyms, nlp_terms, noun_chunks, pattern_matches)
        nlp_term_set = {str(t.get("term") or "").lower() for t in nlp_terms}
        return self.scorer.score_terms(merged, text, nlp_term_set)

    def _extract_ner_terms(self, doc) -> List[Dict[str, Any]]:
        terms: List[Dict[str, Any]] = []
        for ent in doc.ents:
            terms.append(
                {
                    "term": ent.text,
                    "type": "multi-word" if len(ent.text.split()) > 1 else "single-word",
                    "span": (ent.start_char, ent.end_char),
                }
            )
        return terms

    def _extract_noun_chunks(self, doc) -> List[Dict[str, Any]]:
        terms: List[Dict[str, Any]] = []
        for chunk in doc.noun_chunks:
            text = chunk.text.strip()
            if text and text.split()[0].lower() in {"the", "a", "an"}:
                text = " ".join(text.split()[1:])
            if text:
                terms.append(
                    {
                        "term": text,
                        "type": "multi-word" if len(text.split()) > 1 else "single-word",
                        "span": (chunk.start_char, chunk.end_char),
                    }
                )
        return terms

    def _extract_pattern_matches(self, doc) -> List[Dict[str, Any]]:
        terms: List[Dict[str, Any]] = []
        for _, start, end in self.matcher(doc):
            span = doc[start:end]
            terms.append(
                {
                    "term": span.text,
                    "type": "multi-word" if len(span.text.split()) > 1 else "single-word",
                    "span": (span.start_char, span.end_char),
                }
            )
        return terms

    def _extract_regex_candidates(self, text: str) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for match in re.finditer(r"\b(?:[A-Z][a-z]+\s+){1,3}[A-Z][a-z]+\b", text):
            term = match.group(0).strip()
            candidates.append(
                {
                    "term": term,
                    "type": "multi-word",
                    "span": (match.start(), match.end()),
                }
            )
        return candidates

    def _merge_candidates(
        self,
        acronyms: List[Dict[str, Any]],
        nlp_terms: List[Dict[str, Any]],
        noun_chunks: List[Dict[str, Any]],
        pattern_matches: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        all_candidates = acronyms + nlp_terms + noun_chunks + pattern_matches
        unique_candidates: Dict[str, Dict[str, Any]] = {}

        for candidate in all_candidates:
            term = str(candidate.get("term") or "").strip()
            if not term:
                continue
            key = term.lower()
            if key not in unique_candidates:
                unique_candidates[key] = candidate
            else:
                existing = unique_candidates[key]
                if "expansion" in candidate and "expansion" not in existing:
                    unique_candidates[key] = candidate

        return self._resolve_overlaps(list(unique_candidates.values()))

    def _resolve_overlaps(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sorted_candidates = sorted(
            candidates,
            key=lambda item: (item.get("span", (0, 0))[0], -len(str(item.get("term") or ""))),
        )

        kept: List[Dict[str, Any]] = []
        for candidate in sorted_candidates:
            span = candidate.get("span", (0, 0))
            overlaps = any(self._spans_overlap(span, c.get("span", (0, 0))) for c in kept)
            if not overlaps:
                kept.append(candidate)

        return kept

    def _spans_overlap(self, span1: Tuple[int, int], span2: Tuple[int, int]) -> bool:
        return not (span1[1] <= span2[0] or span2[1] <= span1[0])
