# Technical Term Detector — Project Report

## Overview

The Technical Term Detector is a Python-based NLP system that automatically identifies technical terms and acronyms in scientific or technical text and resolves their definitions from structured external knowledge sources. It is designed to process paragraphs from research papers, technical documents, or any domain-specific text and return a ranked, structured JSON output of every detected term alongside its definition and the source from which that definition was retrieved.

The system requires no API keys. All external lookups use publicly available REST APIs. Terms that cannot be resolved automatically are queued into a JSON file for deferred enrichment by a large language model (LLM) at a later stage.

---

## System Architecture

The system is split into five focused Python modules, each with a single responsibility. They are wired together through a central entrypoint.

```
Input Text
    │
    ▼
┌─────────────────────────────────────────┐
│         TechnicalTermDetector           │  detector.py
│                                         │
│  ┌─────────────────┐                    │
│  │ AcronymExtractor│  acronym_extractor │
│  └────────┬────────┘                    │
│           │                             │
│  ┌────────▼────────┐                    │
│  │  SciSpaCy NER   │  en_core_sci_lg    │
│  └────────┬────────┘                    │
│           │                             │
│  ┌────────▼────────┐                    │
│  │   Noun Chunks   │  spaCy built-in    │
│  └────────┬────────┘                    │
│           │                             │
│  ┌────────▼────────┐                    │
│  │  POS Patterns   │  spaCy Matcher     │
│  └────────┬────────┘                    │
│           │                             │
│  ┌────────▼────────┐                    │
│  │   TermScorer    │  scorer.py         │
│  └────────┬────────┘                    │
└───────────┼─────────────────────────────┘
            │  Scored & filtered terms
            ▼
┌─────────────────────────────────────────┐
│          DefinitionLookup               │  definition_lookup.py
│                                         │
│  1. Wikipedia REST API                  │
│  2. CSO (Computer Science Ontology)     │
│  3. Deferred LLM Queue (JSON file)      │
└───────────┬─────────────────────────────┘
            │
            ▼
       JSON Output
```

---

## Module Breakdown

### 1. `acronym_extractor.py` — Acronym Extraction

**Class:** `AcronymExtractor`

This module handles the detection of acronyms using two regular expression passes over the raw input text.

**Pass 1 — Expanded Acronyms**

Matches patterns of the form `Full Name (ABC)`, where the full name is a sequence of title-cased words followed by a 2–6 character uppercase abbreviation in parentheses. Both the acronym and its expansion are recorded and linked together.

Pattern used:
```
([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(([A-Z]{2,6})\)
```

**Pass 2 — Standalone Acronyms**

Scans for uppercase sequences of 2–6 characters that were not already captured in Pass 1. A blocklist of common English words that happen to appear in capitals (such as `THE`, `AND`, `FOR`, `CAN`) is used to suppress false positives.

Output per acronym:
```json
{
  "term": "CNN",
  "type": "acronym",
  "expansion": "Convolutional Neural Network",
  "span": [14, 17]
}
```

---

### 2. `detector.py` — Core Detection Pipeline

**Class:** `TechnicalTermDetector`

This is the main orchestrator for term detection. It loads the NLP model, runs all four extraction strategies in sequence, merges the results, resolves overlapping spans, and hands off to the scorer.

#### Model Loading

The preferred model is `en_core_sci_lg` from the SciSpaCy library, a large spaCy model trained on biomedical and scientific literature. It has significantly better named entity recognition for technical terminology than general-purpose models. If it is not installed, the pipeline falls back to spaCy's `en_core_web_sm`.

#### Step 1 — Acronym Extraction

Delegates to `AcronymExtractor.extract_acronyms()` as described above.

#### Step 2 — SciSpaCy Named Entity Recognition (NER)

Runs the loaded spaCy model on the input text and collects all detected named entities. Because `en_core_sci_lg` was trained on scientific text, its NER recognises terms like `gradient descent`, `neural network`, `vector store`, and `RAG` that standard models would miss or mislabel. Each entity records its text, its type (single-word or multi-word), and its character span.

Terms detected by NER receive preferential treatment during scoring — common English words are not filtered out if SciSpaCy explicitly identified them.

#### Step 3 — Noun Chunk Extraction

Iterates over `doc.noun_chunks` (spaCy's built-in noun phrase chunker). Leading determiners (`the`, `a`, `an`) are stripped from the beginning of each chunk. This step catches multi-word technical phrases that NER may not tag as named entities.

#### Step 4 — POS Pattern Matching

Uses spaCy's `Matcher` with five hand-crafted part-of-speech patterns to extract additional compound terms:

| Pattern Name  | Structure               | Example                        |
|---------------|-------------------------|--------------------------------|
| ADJ_NOUN      | ADJ + NOUN              | dense embedding                |
| NOUN_NOUN     | NOUN + NOUN             | vector store                   |
| NOUN_NOUN_NOUN| NOUN + NOUN + NOUN      | hybrid retrieval framework     |
| NOUN_OF_NOUN  | NOUN + of + NOUN        | retrieval-augmented generation |
| ADJ_ADJ_NOUN  | ADJ + ADJ + NOUN        | pre-trained language model     |

#### Step 5 — Candidate Merging and Deduplication

All extracted candidates from all four sources are merged into a single list. Exact text duplicates are collapsed (keeping the entry that carries the most information, such as an acronym expansion). Overlapping character spans are then resolved by keeping the longest match in any overlapping region.

---

### 3. `scorer.py` — Scoring and Filtering

**Class:** `TermScorer`

Each surviving candidate is scored on a scale from 0 to 1 using three weighted components:

#### Score Formula

$$\text{score} = 0.30 \times \text{freq\_normalized} + 0.50 \times \text{rarity} + 0.20 \times \text{length\_bonus}$$

| Component         | Weight | Description |
|-------------------|--------|-------------|
| `freq_normalized` | 30%    | How often the term appears in the input text, normalised by the maximum frequency of any candidate. Rewards repeated terms as likely important. |
| `rarity`          | 50%    | Inverse of the term's general English frequency from the `wordfreq` library. A term like `GPU` or `Qdrant` scores high; a term like `method` scores low. |
| `length_bonus`    | 20%    | `min(word_count, 3) / 3`. Multi-word terms (up to three words) receive greater weight than single-word terms since technical concepts are often compound. |

#### Filtering Rules

Before scoring, candidates are discarded if they match any of the following:

- Fewer than 2 characters in length.
- Pure English stopwords (e.g., `the`, `and`, `is`).
- Generic academic phrases from a curated blocklist (e.g., `proposed method`, `in this paper`, `results show`, `we present`).
- Single-word common English terms (those with `wordfreq` frequency above `0.0001`) unless SciSpaCy explicitly detected them as named entities.

After scoring, any term with a final score below `0.30` is discarded. The surviving terms are returned sorted by score descending.

---

### 4. `definition_lookup.py` — Definition Lookup

**Class:** `DefinitionLookup`

This module implements a cascading lookup strategy across multiple external knowledge sources. Each source is tried in priority order; the first successful result is returned immediately.

#### Layer 1 — Inline Definition Search (when full text is available)

Scans the source document for patterns that signal the author has defined the term themselves. Regular expressions match seven definition patterns:

```
"<term>, which is ..."
"<term>, defined as ..."
"<term> (explanation)"
"<term>, i.e., ..."
"<term>, also known as ..."
"<term>, refers to ..."
"<term>: ..."
```

This layer is instant (no network call) and yields the most contextually accurate definition because it comes from the paper itself.

#### Layer 2 — Wikipedia REST API

Queries the Wikipedia REST API v1 endpoint at  
`/api/rest_v1/page/summary/{term}`.

1. A direct lookup by term name is attempted first.
2. If that returns no result or a disambiguation page, an OpenSearch query to the MediaWiki API is made to find the correct page title.
3. The first sentence of the summary extract is returned as the definition.

No API key is required. The `User-Agent` header is set to `TechnicalTermDetector/1.0 (Educational Project)` as required by the Wikimedia API guidelines. Requests time out after 5 seconds.

#### Layer 3 — Computer Science Ontology (CSO)

Queries the CSO API at `https://cso.kmi.open.ac.uk/api/v2.0/topics`. CSO is a large-scale ontology of research areas in computer science maintained by The Open University's Knowledge Media Institute. If the term is found and has an abstraction field, a definition sentence is synthesised.

For terms with physics-specific keywords (e.g., `quantum`, `higgs`, `boson`, `relativity`), the INSPIRE-HEP literature API is also queried as a supplementary step within this layer.

#### Layer 4 — Deferred LLM Queue

If all lookup layers fail, the term is marked with `"queued_for_llm": true` in the output and appended to a pending terms list. This list is serialised to a JSON file at the end of each run. It records the term, its type, score, the context sentence in which it appeared, and which lookup sources were already attempted. This queue can be fed to any LLM in a later batch step without re-running the full pipeline.

---

### 5. `technical_term_system.py` — System Entrypoint

This module wires all components together and exposes both a programmatic API and a CLI.

#### Processing Flow

```
_read_input_payload()
        │
        ▼
_parse_payload()          → extract list of text_blocks
        │
        ▼
run_system()
  └── for each text_block:
        process_text_block()
          │
          ├── TechnicalTermDetector.detect()
          │       └── returns all candidates, scored
          │
          ├── filter by min_score (default: 0.65)
          │
          └── for each surviving term:
                _lookup_definition_final_strategy()
                  ├── Wikipedia
                  ├── CSO
                  └── → deferred LLM queue if unresolved
        │
        ▼
_write_json_file()        → pending_llm_terms.json
        │
        ▼
JSON output to stdout or --output-json
```

#### Score Threshold

Only terms with a detector score of `0.65` or above are forwarded for definition lookup (configurable via `--min-score`). This threshold is above the internal scoring floor of `0.30` and selects only the most clearly technical candidates to avoid flooding the output with borderline terms.

#### Output Structure

Each run produces a JSON object of the following shape:

```json
{
  "system": "technical_term_detector_final",
  "definition_strategy": ["wikipedia", "cso", "deferred_llm_queue"],
  "generated_at": "2026-03-15T10:00:00+00:00",
  "num_text_blocks": 1,
  "pending_llm_terms_count": 2,
  "pending_llm_terms_file": "/path/to/pending_llm_terms.json",
  "results": [
    {
      "text_length": 412,
      "detected_terms": 18,
      "returned_terms": 9,
      "min_score": 0.65,
      "lookup_time_total": 3.14,
      "queued_for_llm_count": 2,
      "source_stats": {
        "wikipedia": 5,
        "cso": 2,
        "queued_for_llm": 2
      },
      "terms": [
        {
          "term": "Qdrant",
          "type": "single-word",
          "score": 0.88,
          "definition": "Qdrant is a vector similarity search engine...",
          "definition_source": "wikipedia",
          "lookup_time": 0.42
        }
      ]
    }
  ]
}
```

---

## Technologies Used

| Technology | Role |
|---|---|
| **Python 3.12** | Runtime language |
| **spaCy** | NLP backbone — tokenisation, POS tagging, noun chunk extraction, Matcher |
| **SciSpaCy (`en_core_sci_lg`)** | Scientific NER model trained on biomedical/CS literature |
| **wordfreq** | English word frequency database — used for rarity scoring |
| **requests** | HTTP client for Wikipedia, CSO, and INSPIRE-HEP API calls |
| **Wikipedia REST API v1** | Primary definition source, free and no key required |
| **CSO API (Open University)** | Computer science ontology, secondary definition source |
| **INSPIRE-HEP API** | High-energy physics literature, supplementary source for physics terms |
| **Ollama (optional)** | Local LLM server, used only in the legacy `get_definition()` method; the main entrypoint defers instead of calling it |
| **argparse** | CLI argument parsing |
| **re** | Regular expressions for acronym extraction and inline definition search |

---

## Installation

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` installs:
- `spacy>=3.0.0`
- `scispacy>=0.5.0`
- `wordfreq>=3.0.0`
- `requests>=2.28.0`

### 2. Install the SciSpaCy model (recommended)

```bash
pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_lg-0.5.4.tar.gz
```

### 3. Install the spaCy fallback model (optional)

```bash
python -m spacy download en_core_web_sm
```

This is used automatically if `en_core_sci_lg` is not found.

---

## Usage

### CLI — single text block

```bash
python technical_term_system.py --text-block "We trained a CNN with gradient descent."
```

### CLI — multiple text blocks

```bash
python technical_term_system.py \
  --text-block "First paragraph of the paper." \
  --text-block "Second paragraph describing methodology."
```

### CLI — JSON input file with output file

```bash
python technical_term_system.py --input-json input.json --output-json output.json
```

### Pipe JSON from stdin

```bash
echo '{"text_block": "We trained a CNN with gradient descent."}' \
  | python technical_term_system.py
```

### Save deferred LLM queue to a specific path

```bash
python technical_term_system.py \
  --text-block "The model uses HyperVectorBridge for orchestration." \
  --pending-llm-json queued_terms.json
```

### Adjust the minimum score threshold

```bash
python technical_term_system.py \
  --text-block "We trained a CNN with gradient descent." \
  --min-score 0.75
```

### Input JSON format

Either a single block:
```json
{ "text_block": "Your paragraph here." }
```

Or multiple blocks:
```json
{
  "text_blocks": [
    "First paragraph.",
    "Second paragraph."
  ]
}
```

---

## File Structure

```
.
├── technical_term_system.py   # Main entrypoint — wires all modules, CLI, I/O
├── detector.py                # TechnicalTermDetector — NER, POS, acronyms, merging
├── scorer.py                  # TermScorer — frequency, rarity, length scoring
├── acronym_extractor.py       # AcronymExtractor — regex-based acronym detection
├── definition_lookup.py       # DefinitionLookup — Wikipedia / CSO / INSPIRE / LLM
├── requirements.txt           # Python package dependencies
└── README.md                  # This document
```

---

## Design Decisions

**Why SciSpaCy over a general spaCy model?**  
General-purpose models like `en_core_web_sm` are trained mainly on news text. They misclassify scientific terms as `PERSON`, `ORG`, or `MISC` entities, or miss them entirely. `en_core_sci_lg` is trained on PubMed and full-text science papers, making it far more accurate for the target domain.

**Why wordfreq for scoring?**  
Statistical word frequency is an effective proxy for technicality. Highly specialised terms like `qdrant`, `scispacy`, or `transformer` have very low general English frequency and score near 1.0 on the rarity component. Common words like `model` or `system` score near 0.0 and are deprioritised accordingly.

**Why defer LLM calls instead of calling them inline?**  
LLM inference — even via a local Ollama server — is slow (1–5 seconds per term) and introduces a hard dependency on a running service. The deferred queue design means the detection step always completes quickly and reliably. LLM enrichment becomes an optional post-processing step that can be run in batch, rate-limited, or skipped entirely.

**Why Wikipedia first?**  
Wikipedia has broad, high-quality coverage of technical terms across CS, physics, mathematics, and engineering. The REST API is fast (typically under 500ms), free, and requires no key. It resolves the large majority of mainstream technical terms correctly with a concise first-sentence summary.
```

### Option 5: Custom deferred LLM queue file

```bash
python technical_term_system.py --text-block "We trained a CNN with gradient descent." --pending-llm-json queued_terms.json
```

## Output Format

Top-level output:

```json
{
   "system": "technical_term_detector_final",
   "definition_strategy": ["wikipedia", "cso", "deferred_llm_queue"],
   "generated_at": "...",
   "num_text_blocks": 1,
   "pending_llm_terms_count": 1,
   "pending_llm_terms_file": "/path/to/pending_llm_terms.json",
   "results": [
      {
         "text_length": 123,
         "detected_terms": 10,
         "returned_terms": 4,
         "min_score": 0.65,
         "lookup_time_total": 1.24,
         "queued_for_llm_count": 1,
         "source_stats": {
            "wikipedia": 2,
            "cso": 1,
            "queued_for_llm": 1,
            "not_found": 0
         },
         "terms": [
            {
               "term": "CNN",
               "type": "acronym",
               "score": 0.95,
               "expansion": "convolutional neural network",
               "definition": null,
               "definition_source": null,
               "queued_for_llm": true,
               "lookup_time": 0.21
            }
         ],
         "text_block_index": 0
      }
   ]
}
```

## Notes

- If no definition is found in Wikipedia or CSO, the term is queued in the deferred LLM JSON file.
- The default deferred queue file is pending_llm_terms.json unless you pass --pending-llm-json or --output-json.
- The core detector and lookup modules are unchanged; technical_term_system.py is the single orchestration entrypoint.
