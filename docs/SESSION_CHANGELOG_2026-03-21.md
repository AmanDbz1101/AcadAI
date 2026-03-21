# Session Changelog - 2026-03-21

## Scope
This document summarizes all major code changes made during this session, the issues encountered, and how they were addressed.

## Chronological Summary of Changes

### 1. Metadata extraction fallback for missing title/abstract
- Implemented additional recovery logic in metadata extraction so that when heuristic title/abstract detection fails, opening text context is used with Groq to recover missing metadata.
- Added prompt/path improvements to better extract title and abstract from early paper content.

### 2. Keyword extraction support across extraction outputs
- Added keyword extraction flow to metadata processing.
- Extended metadata model and output serialization to include keywords in generated metadata JSON.
- Updated extraction output paths to persist keywords in complete output payloads.

### 3. Enforced abstract-required behavior
- Tightened extraction behavior so empty/invalid abstract is treated as a hard failure condition in metadata extraction (abstract required for downstream graph stages).

### 4. Expanded context and prompt quality for extraction
- Increased opening-context size and refined prompt instructions to improve extraction of abstract and keywords from first sections/paragraphs.

### 5. Theory paper resilience fixes (temporary phase)
- Introduced additional resilience during theory-paper debugging when extraction quality and LLM availability were poor.
- Included fallback/recovery logic intended to avoid pipeline breaks under adverse conditions.
- Adjusted ingestion/ocr behavior during this troubleshooting phase.

### 6. User-requested rollback of theory-specific fixes
- Reverted theory-specific workaround logic after user request to restore prior baseline behavior.
- Rolled back targeted sections in metadata/ingestion where theory-only recovery behavior had been introduced.
- Preserved broader non-theory improvements requested earlier (keywords, abstract-required policy, improved prompts/context).

### 7. Guide generation schema consistency fix
- Identified that guide outputs were inconsistent when LLM guide generation was rate-limited.
- Root cause: fallback guide path emitted a minimal flat JSON shape instead of category Pydantic pass-based shape.
- Updated fallback guide builder to emit structured three-pass schema matching model-aligned output contract.
- Re-ran theory pipeline and validated new fallback output follows expected structured guide format.

### 8. Survey metadata title/abstract accuracy restoration
- Investigated regression where `survey.pdf` metadata showed incorrect title (`. Invited Review .`) and noisy abstract content (title/authors/keywords mixed into abstract).
- Root cause analysis:
  - LLM prompt allowed document-type labels and front-matter noise to be interpreted as title.
  - Title recovery only retried when title was empty/unknown, so low-quality non-empty titles were accepted.
  - Opening context passed to Groq contained OCR/markup noise (including `GLYPH<...>` artifacts), degrading extraction quality.
  - Groq 429 rate limits increased fallback usage, exposing weaker heuristics.
- Fixes implemented in `backend/extraction/app/metadata_extractor.py`:
  - Strengthened extraction prompts to explicitly exclude document labels, author names, affiliations, and keyword lists from title/abstract.
  - Added title normalization and quality validation helpers.
  - Added heading-based title fallback selection when LLM output is weak/invalid.
  - Improved opening-context construction with noise cleanup before sending text to LLM.
  - Added title+abstract post-processing to remove duplicated title prefixes, author/affiliation preambles, OCR artifacts, and trailing keyword-list tails.
- Result:
  - `survey.pdf` title restored to `Pre-trained Models for Natural Language Processing: A Survey`.
  - Abstract became a clean summary paragraph rather than front-matter metadata text.

## Issues Faced and Resolutions

### Issue A: Groq rate limits (HTTP 429, token/day limits)
- Symptoms:
  - Metadata inference/classification intermittently failed due to token/day limits.
  - Guide generation frequently hit rate limits and fell back.
- Resolution:
  - Added and used fallback paths where needed.
  - Final guide fallback was upgraded to structured schema to avoid contract drift.

### Issue B: Poor/garbled extracted text from specific theory PDF
- Symptoms:
  - Low quality content in some extraction paths (font-encoded/garbled patterns) affected metadata quality.
- Resolution:
  - Temporary resilience work was introduced for debugging.
  - Later rolled back theory-specific workaround code per user request.
  - Baseline extraction remained with abstract-required behavior and improved context/prompt logic.

### Issue C: Guide output looked incomplete/different from expected model
- Symptoms:
  - Guide JSON contained only fallback/category/questions/sections fields and lacked pass-based structure.
- Root Cause:
  - Rate-limit fallback branch bypassed Pydantic structured model output and wrote an ad-hoc JSON.
- Resolution:
  - Refactored fallback guide generation to output the same structured pass-based schema used by normal model outputs.
  - Verified regenerated guide now contains pass1/pass2/pass3 and final task structure.

### Issue D: Tooling friction in workspace (search utility)
- Symptoms:
  - `rg` (ripgrep) was unavailable in terminal.
- Resolution:
  - Switched to grep/find-based search commands for investigation.

### Issue E: Title/abstract drift under fallback-heavy runs
- Symptoms:
  - Title selected as generic header label (`Invited Review`) instead of actual paper title.
  - Abstract included author block and keyword tail.
- Root Cause:
  - Validation logic treated any non-empty title as acceptable.
  - Prompt/context lacked strict exclusion of front-matter noise.
  - OCR artifact tokens and noisy first-page text polluted extraction context.
- Resolution:
  - Added strict title validity checks plus heading-based recovery.
  - Refined prompt instructions and cleaned opening context.
  - Added final abstract cleanup and structured post-processing.

## Validation Performed
- Repeated syntax checks using py_compile on modified Python files.
- End-to-end pipeline runs executed against theory2 PDF.
- Output verification confirmed structured fallback guide JSON shape after latest fix.
- Re-ran end-to-end pipeline on `input/survey.pdf` after each metadata patch.
- Verified generated `output/e0960904-0d88-57cb-a52e-f60e01df2c7b_complete.json` now contains corrected title and improved abstract text.

## Key Outcome
By the end of the session, fallback guide generation is now contract-consistent with expected structured guide models even under LLM rate limiting, and theory-specific workaround code was rolled back as requested while keeping broader requested extraction improvements.