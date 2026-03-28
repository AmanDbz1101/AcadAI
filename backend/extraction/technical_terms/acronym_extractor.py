"""Acronym extraction for technical-term detection."""

from __future__ import annotations

import re
from typing import Any, Dict, List


class AcronymExtractor:
    """Extract acronyms from scientific text."""

    def __init__(self) -> None:
        self.expanded_pattern = re.compile(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(([A-Z]{2,6})\)"
        )
        self.standalone_pattern = re.compile(r"\b[A-Z]{2,6}\b")

    def extract_acronyms(self, text: str) -> List[Dict[str, Any]]:
        acronyms: List[Dict[str, Any]] = []
        seen_acronyms = set()

        for match in self.expanded_pattern.finditer(text):
            expansion = match.group(1)
            acronym = match.group(2)
            acronyms.append(
                {
                    "term": acronym,
                    "type": "acronym",
                    "expansion": expansion,
                    "span": (match.start(2), match.end(2)),
                }
            )
            seen_acronyms.add(acronym)

        for match in self.standalone_pattern.finditer(text):
            acronym = match.group(0)
            if self._is_likely_acronym(acronym) and acronym not in seen_acronyms:
                acronyms.append(
                    {
                        "term": acronym,
                        "type": "acronym",
                        "span": (match.start(), match.end()),
                    }
                )
                seen_acronyms.add(acronym)

        return acronyms

    def _is_likely_acronym(self, text: str) -> bool:
        common_words = {
            "THE",
            "AND",
            "FOR",
            "ARE",
            "BUT",
            "NOT",
            "YOU",
            "ALL",
            "CAN",
            "HER",
            "WAS",
            "ONE",
            "OUR",
            "OUT",
            "DAY",
            "GET",
            "HAS",
            "HIM",
            "HIS",
            "HOW",
            "ITS",
            "MAY",
            "NEW",
            "NOW",
            "OLD",
            "SEE",
            "TWO",
            "WAY",
            "WHO",
            "BOY",
            "DID",
            "GOT",
            "LET",
            "PUT",
            "SAY",
            "SHE",
            "TOO",
            "USE",
            "YES",
        }
        return text not in common_words
