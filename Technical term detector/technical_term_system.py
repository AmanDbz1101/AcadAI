#!/usr/bin/env python3
"""
Single entrypoint system for technical term detection and definition lookup.

Input:
- JSON payload with either:
  - {"text_block": "..."}
  - {"text_blocks": ["...", "..."]}

Output:
- JSON result with detected terms and definitions.

Definition strategy used by this entrypoint:
1. Wikipedia
2. CSO (Computer Science Ontology)
3. Deferred LLM queue written to JSON for later processing
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from definition_lookup import DefinitionLookup
from detector import TechnicalTermDetector


def _extract_context_sentence(text: str, term: str) -> str:
    """Return a sentence containing the term, if available."""
    term_lower = term.lower()
    sentences = re.split(r"(?<=[.!?])\s+", text)

    for sentence in sentences:
        if term_lower in sentence.lower():
            return sentence.strip()

    return ""


def _build_pending_llm_record(
    term_info: Dict[str, Any],
    context_sentence: str,
    text_block_index: int,
    lookup_time: float,
) -> Dict[str, Any]:
    """Build a queue record for a term that still needs LLM enrichment."""
    pending_record: Dict[str, Any] = {
        "term": term_info["term"],
        "type": term_info.get("type"),
        "score": term_info.get("score"),
        "text_block_index": text_block_index,
        "context_sentence": context_sentence,
        "lookup_time": lookup_time,
        "lookup_sources_attempted": ["wikipedia", "cso"],
    }

    if term_info.get("expansion"):
        pending_record["expansion"] = term_info["expansion"]

    return pending_record


def _lookup_definition_final_strategy(
    lookup: DefinitionLookup,
    term: str,
) -> Dict[str, Any]:
    """
    Lookup definition using final strategy: Wikipedia -> CSO -> deferred LLM queue.
    """
    started = time.time()

    definition = lookup._get_wikipedia_definition(term)
    if definition:
        return {
            "definition": definition,
            "source": "wikipedia",
            "time_taken": round(time.time() - started, 4),
        }

    definition = lookup._get_cso_definition(term)
    if definition:
        return {
            "definition": definition,
            "source": "cso",
            "time_taken": round(time.time() - started, 4),
        }

    return {
        "definition": None,
        "source": None,
        "time_taken": round(time.time() - started, 4),
        "status": "queued_for_llm",
    }


def process_text_block(
    text_block: str,
    detector: Optional[TechnicalTermDetector] = None,
    min_score: float = 0.65,
    text_block_index: int = 0,
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Process one text block and return detected terms with definitions.
    """
    if not isinstance(text_block, str) or not text_block.strip():
        raise ValueError("Each text_block must be a non-empty string.")

    detector_instance = detector if detector is not None else TechnicalTermDetector()
    lookup = DefinitionLookup()

    detected_terms = detector_instance.detect(text_block)
    selected_terms = [term for term in detected_terms if term.get("score", 0.0) >= min_score]

    output_terms: List[Dict[str, Any]] = []
    pending_llm_terms: List[Dict[str, Any]] = []
    source_stats = {
        "wikipedia": 0,
        "cso": 0,
        "queued_for_llm": 0,
        "not_found": 0,
    }

    for term_info in selected_terms:
        term = term_info["term"]
        context_sentence = _extract_context_sentence(text_block, term)
        lookup_result = _lookup_definition_final_strategy(lookup, term)

        source = lookup_result.get("source")
        if source in source_stats:
            source_stats[source] += 1
        elif lookup_result.get("status") == "queued_for_llm":
            source_stats["queued_for_llm"] += 1
        else:
            source_stats["not_found"] += 1

        term_record: Dict[str, Any] = {
            "term": term,
            "type": term_info.get("type"),
            "score": term_info.get("score"),
            "definition": lookup_result.get("definition"),
            "definition_source": source,
            "lookup_time": lookup_result.get("time_taken"),
        }

        if term_info.get("expansion"):
            term_record["expansion"] = term_info["expansion"]

        if lookup_result.get("status") == "queued_for_llm":
            term_record["queued_for_llm"] = True
            pending_llm_terms.append(
                _build_pending_llm_record(
                    term_info=term_info,
                    context_sentence=context_sentence,
                    text_block_index=text_block_index,
                    lookup_time=lookup_result["time_taken"],
                )
            )

        output_terms.append(term_record)

    total_lookup_time = round(sum(term["lookup_time"] for term in output_terms), 4)

    return {
        "text_length": len(text_block),
        "detected_terms": len(detected_terms),
        "returned_terms": len(output_terms),
        "min_score": min_score,
        "lookup_time_total": total_lookup_time,
        "queued_for_llm_count": len(pending_llm_terms),
        "source_stats": source_stats,
        "terms": output_terms,
        "text_block_index": text_block_index,
    }, pending_llm_terms


def run_system(text_blocks: Sequence[str], min_score: float = 0.65) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Run the full system on one or more text blocks."""
    if not text_blocks:
        raise ValueError("No text blocks provided.")

    detector = TechnicalTermDetector()
    generated_at = datetime.now(timezone.utc).isoformat()
    pending_llm_terms: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []

    for index, text_block in enumerate(text_blocks):
        block_result, block_pending_llm_terms = process_text_block(
            text_block,
            detector=detector,
            min_score=min_score,
            text_block_index=index,
        )
        results.append(block_result)
        pending_llm_terms.extend(block_pending_llm_terms)

    return {
        "system": "technical_term_detector_final",
        "definition_strategy": ["wikipedia", "cso", "deferred_llm_queue"],
        "generated_at": generated_at,
        "num_text_blocks": len(results),
        "pending_llm_terms_count": len(pending_llm_terms),
        "results": results,
    }, pending_llm_terms


def _resolve_pending_llm_json_path(
    output_json: Optional[str],
    pending_llm_json: Optional[str],
) -> Path:
    """Resolve the JSON file path used for deferred LLM terms."""
    if pending_llm_json:
        return Path(pending_llm_json).expanduser()

    if output_json:
        output_path = Path(output_json).expanduser()
        return output_path.with_name(f"{output_path.stem}_pending_llm_terms.json")

    return Path("pending_llm_terms.json")


def _build_pending_llm_payload(
    pending_llm_terms: Sequence[Dict[str, Any]],
    generated_at: str,
) -> Dict[str, Any]:
    """Build the persisted payload for terms queued for later LLM processing."""
    return {
        "system": "technical_term_detector_final",
        "generated_at": generated_at,
        "definition_strategy": ["wikipedia", "cso", "deferred_llm_queue"],
        "count": len(pending_llm_terms),
        "terms": list(pending_llm_terms),
    }


def _write_json_file(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON payload to disk, creating parent directories when needed."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _parse_payload(payload: Dict[str, Any]) -> List[str]:
    """Extract text blocks from input JSON payload."""
    if "text_block" in payload:
        text_block = payload["text_block"]
        if not isinstance(text_block, str):
            raise ValueError("text_block must be a string.")
        return [text_block]

    if "text_blocks" in payload:
        text_blocks = payload["text_blocks"]
        if not isinstance(text_blocks, list) or not all(isinstance(item, str) for item in text_blocks):
            raise ValueError("text_blocks must be a list of strings.")
        return text_blocks

    raise ValueError("Input JSON must contain text_block or text_blocks.")


def _read_input_payload(args: argparse.Namespace) -> Dict[str, Any]:
    """Read input payload from args, file, or stdin."""
    if args.text_block:
        if len(args.text_block) == 1:
            return {"text_block": args.text_block[0]}
        return {"text_blocks": args.text_block}

    if args.input_json:
        with open(args.input_json, "r", encoding="utf-8") as handle:
            return json.load(handle)

    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if not raw:
            raise ValueError("Stdin is empty. Provide JSON with text_block or text_blocks.")
        return json.loads(raw)

    raise ValueError("No input provided. Use --text-block, --input-json, or stdin JSON.")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Process text_block/text_blocks and return JSON with technical terms and definitions."
    )
    parser.add_argument(
        "--text-block",
        action="append",
        help="Text block input. Repeat this flag for multiple blocks.",
    )
    parser.add_argument(
        "--input-json",
        help="Path to JSON input file containing text_block or text_blocks.",
    )
    parser.add_argument(
        "--output-json",
        help="Path to write JSON output. If omitted, output is printed to stdout.",
    )
    parser.add_argument(
        "--pending-llm-json",
        help=(
            "Path to write terms that were not resolved by Wikipedia/CSO and should be sent "
            "to an LLM later. Defaults to pending_llm_terms.json or a sibling of --output-json."
        ),
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.65,
        help="Minimum detector score to include a term (default: 0.65).",
    )
    return parser


def main() -> None:
    """CLI entrypoint."""
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        payload = _read_input_payload(args)
        text_blocks = _parse_payload(payload)
        output, pending_llm_terms = run_system(text_blocks, min_score=args.min_score)

        pending_llm_json_path = _resolve_pending_llm_json_path(args.output_json, args.pending_llm_json)
        pending_llm_payload = _build_pending_llm_payload(pending_llm_terms, output["generated_at"])
        _write_json_file(pending_llm_json_path, pending_llm_payload)

        output["pending_llm_terms_file"] = str(pending_llm_json_path.resolve())
    except Exception as exc:
        error_output = {
            "error": str(exc),
            "status": "failed",
        }
        print(json.dumps(error_output, indent=2, ensure_ascii=False))
        sys.exit(1)

    rendered = json.dumps(output, indent=2, ensure_ascii=False)

    if args.output_json:
        _write_json_file(Path(args.output_json).expanduser(), output)

    print(rendered)


if __name__ == "__main__":
    main()
