"""Definition lookup utilities for technical terms."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import quote

import requests


class DefinitionLookup:
    """Lookup definitions from external APIs without LLM fallback."""

    def lookup_api_definition(self, term: str) -> Tuple[Optional[str], Optional[str]]:
        definition = self._get_dbpedia_definition(term)
        if definition:
            return definition, "dbpedia"

        definition = self._get_dictionary_definition(term)
        if definition:
            return definition, "dictionary"

        definition = self._get_wikipedia_definition(term)
        if definition:
            return definition, "wikipedia"

        return None, None

    def _get_dbpedia_definition(self, term: str) -> Optional[str]:
        try:
            endpoint = "http://dbpedia.org/sparql"
            query = """
                SELECT ?abstract WHERE {
                  ?resource rdfs:label ?label ;
                            dbo:abstract ?abstract .
                  FILTER (lang(?label) = 'en')
                  FILTER (lang(?abstract) = 'en')
                  FILTER (lcase(str(?label)) = lcase(?term))
                }
                LIMIT 1
            """
            params = {
                "query": query,
                "format": "application/sparql-results+json",
                "term": term.strip(),
            }
            response = requests.get(endpoint, params=params, timeout=6)
            if response.status_code != 200:
                return None

            data = response.json()
            bindings = data.get("results", {}).get("bindings", [])
            if not bindings:
                return None

            abstract = str(bindings[0].get("abstract", {}).get("value") or "").strip()
            if not abstract:
                return None

            sentence = abstract.split(". ")[0].strip()
            if len(sentence) < 20:
                return None
            if not sentence.endswith("."):
                sentence += "."
            return sentence
        except Exception:  # noqa: BLE001
            return None

    def _get_dictionary_definition(self, term: str) -> Optional[str]:
        try:
            clean_term = quote(term.strip().lower())
            if not clean_term:
                return None

            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{clean_term}"
            response = requests.get(url, timeout=6)
            if response.status_code != 200:
                return None

            data = response.json()
            if not isinstance(data, list) or not data:
                return None

            first_entry = data[0] if isinstance(data[0], dict) else {}
            meanings = first_entry.get("meanings") or []
            for meaning in meanings:
                definitions = meaning.get("definitions") or []
                for definition_item in definitions:
                    definition = str(definition_item.get("definition") or "").strip()
                    if len(definition) > 8:
                        if not definition.endswith("."):
                            definition += "."
                        return definition

            return None
        except Exception:  # noqa: BLE001
            return None

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

