"""Definition lookup utilities for technical terms."""

from __future__ import annotations

import re
from typing import Optional, Tuple

import requests


class DefinitionLookup:
    """Lookup definitions from external APIs without LLM fallback."""

    def lookup_api_definition(self, term: str) -> Tuple[Optional[str], Optional[str]]:
        definition = self._get_cso_definition(term)
        if definition:
            return definition, "cso"

        definition = self._get_inspire_definition(term)
        if definition:
            return definition, "inspire"

        definition = self._get_wikipedia_definition(term)
        if definition:
            return definition, "wikipedia"

        return None, None

    def _get_wikipedia_definition(self, term: str) -> Optional[str]:
        try:
            term_cleaned = term.replace(" ", "_")
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{term_cleaned}"
            headers = {"User-Agent": "ResearchPaperAssistant/1.0"}

            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                extract = str(data.get("extract") or "")
                if extract and not extract.startswith("Wikimedia disambiguation page"):
                    first_sentence = extract.split(". ")[0].strip()
                    if len(first_sentence) > 20:
                        if not first_sentence.endswith("."):
                            first_sentence += "."
                        return first_sentence

            search_url = "https://en.wikipedia.org/w/api.php"
            search_params = {
                "action": "opensearch",
                "search": term,
                "limit": 1,
                "namespace": 0,
                "format": "json",
            }
            response = requests.get(search_url, params=search_params, headers=headers, timeout=5)
            if response.status_code != 200:
                return None

            search_results = response.json()
            if not (isinstance(search_results, list) and len(search_results) > 1 and search_results[1]):
                return None

            page_title = str(search_results[1][0])
            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{page_title.replace(' ', '_')}"
            response = requests.get(summary_url, headers=headers, timeout=5)
            if response.status_code != 200:
                return None

            data = response.json()
            extract = str(data.get("extract") or "")
            if extract and not extract.startswith("Wikimedia disambiguation page"):
                first_sentence = extract.split(". ")[0].strip()
                if len(first_sentence) > 20:
                    if not first_sentence.endswith("."):
                        first_sentence += "."
                    return first_sentence

            return None
        except Exception:  # noqa: BLE001
            return None

    def _get_cso_definition(self, term: str) -> Optional[str]:
        try:
            url = "https://cso.kmi.open.ac.uk/api/v2.0/topics"
            params = {"topic": term.lower()}
            response = requests.get(url, params=params, timeout=5)
            if response.status_code != 200:
                return None

            data = response.json()
            if isinstance(data, dict):
                abstraction = str(data.get("abstraction") or "").strip()
                if abstraction:
                    return f"A computer science topic related to {abstraction}."

                explanation = str(data.get("description") or "").strip()
                if explanation:
                    return explanation

            return None
        except Exception:  # noqa: BLE001
            return None

    def _get_inspire_definition(self, term: str) -> Optional[str]:
        try:
            url = "https://inspirehep.net/api/literature"
            params = {
                "q": f'title:"{term}"',
                "size": 1,
                "fields": "abstracts,titles",
                "sort": "mostrecent",
            }
            response = requests.get(url, params=params, timeout=5)
            if response.status_code != 200:
                return None

            data = response.json()
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                return None

            metadata = hits[0].get("metadata", {})
            titles = metadata.get("titles", [])
            if titles:
                title_text = str(titles[0].get("title") or "").lower()
                term_lower = term.lower()
                if term_lower not in title_text:
                    return None

            abstracts = metadata.get("abstracts", [])
            if not abstracts:
                return None

            abstract_text = str(abstracts[0].get("value") or "").strip()
            if not abstract_text:
                return None

            sentences = re.split(r"(?<=[.!?])\s+", abstract_text)
            first_sentence = (sentences[0] if sentences else "").strip()
            if len(first_sentence) > 50:
                if not first_sentence.endswith("."):
                    first_sentence += "."
                return first_sentence

            return None
        except Exception:  # noqa: BLE001
            return None
