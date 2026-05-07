Fixes implemented (May 2026)

Summary
-------
This document lists the minimal code changes made to address two confirmed performance/ordering bugs and one UX edge-case. Each entry links to the file changed and describes the rationale.

Fix 1A — Run DDL/schema initialization only once per process
---------------------------------------------------------
- Problem: `ensure_schema()` called on many read requests caused repeated DDL and `create_all()` activity over the DB connection.
- Change: Added a process-global guard so schema creation / lightweight migration runs only once per process.
- Files changed:
  - [backend/extraction/persistence/postgres_store.py](backend/extraction/persistence/postgres_store.py#L33-L36) — added `_schema_initialized` flag
  - [backend/extraction/persistence/postgres_store.py](backend/extraction/persistence/postgres_store.py#L348-L388) — wrapped `ensure_schema()` body with a fast-path check, debug log when skipping, and an info log when initialization runs.
- Rationale: avoids network round-trips and DDL checks on every API call.

Fix 1B — Avoid fetching `text_content` twice for bundle responses
---------------------------------------------------------------
- Problem: The bundle endpoint fetched `text_blocks` (including `text_content`) and also executed a join `section_text_blocks -> text_blocks` that selected `text_content` again, duplicating large text payloads.
- Change: Stop selecting `text_content` in the section join and build `section_text_map` from the already-loaded `text_blocks` lookup in the bundle handler.
- Files changed:
  - [backend/extraction/persistence/postgres_store.py](backend/extraction/persistence/postgres_store.py#L1151-L1169) — removed `TextBlockRecord.text_content` from the SELECT in `get_section_text_blocks_for_paper_id`.
  - [backend/api/app.py](backend/api/app.py#L1119-L1134) — bundle handler now builds a `tb_lookup` from `text_blocks` and uses it to populate section content, avoiding re-fetching large text columns.
- Rationale: reduces DB network traffic and memory duplication for typical papers with many text blocks.

Fix 1C — Disable blocking external HTTP calls during bundle requests (Option A)
-------------------------------------------------------------------------------
- Problem: `extract_technical_terms_for_bundle()` performed multiple blocking HTTP requests (DBpedia, Wikipedia, dictionaryapi) synchronously inside the bundle request, causing 20–60 external requests and long response times.
- Change: Temporarily disable technical-term extraction in the synchronous bundle endpoint (Option A). When the feature flag is enabled we now skip work and log an informational message.
- Files changed:
  - [backend/api/app.py](backend/api/app.py#L1176-L1184) — technical terms set to empty and an info log added; comment included noting Option B (proper fix) is to move this to a separate cached endpoint.
- Rationale: Fastest safe fix to restore bundle latency. Full solution (Option B) would add a cached `/api/papers/{id}/terms` endpoint and persist results.

Fix 2 — Generate reading guide before heavy indexing
---------------------------------------------------
- Problem: Background pipeline generated the guide only after long Qdrant indexing, delaying when the UI could show the guide.
- Change: Moved guide generation step to occur immediately after extraction and DB persistence, before `_index_paper_in_qdrant(...)`. Added progress updates and phase logging reflecting the new order.
- Files changed:
  - [backend/api/app.py](backend/api/app.py#L558-L606) — `_extract_and_update_paper()` now runs guide generation (phase 1c) prior to indexing (phase 2); logs added for phases.
- Rationale: UI should be able to show reading guide quickly; indexing can run after the guide is visible.

Fix 3 — Duplicate upload: schedule guide-only generation when appropriate
-------------------------------------------------------------------------
- Problem: When `create_pending_paper()` detected a duplicate (paper already exists), the code did not schedule background tasks at all. That prevented guide regeneration or progress updates on duplicates.
- Change: For duplicate uploads, if the stored `paper_guide` is missing or empty, schedule `_generate_and_store_reading_guide(paper_id)` as a background task. Leave full extraction/indexing skipped for true duplicates.
- Files changed:
  - [backend/api/app.py](backend/api/app.py#L1496-L1528) — upload handler checks existing guide row and schedules guide-only generation with `background_tasks.add_task(...)` when missing.
- Rationale: ensures users who re-upload a duplicate still get guide generation when needed, and progress events are produced.

Notes & Validation
------------------
- The changes were intentionally minimal and focused only on the fixes requested. No refactorings or unrelated changes were made.
- After deployment, verify the following in logs for a new upload:
  - "Schema initialized (will not run again this process)" appears once on startup or first relevant request.
  - Progress events show phases in this order: `extraction` → `guide` → `indexing`.
  - Bundle responses no longer perform external HTTP calls for technical terms; a log entry will indicate skipping when the feature flag is true.

Next steps (optional)
---------------------
- Implement Option B: add a cached `GET /api/papers/{id}/terms` endpoint and background pre-computation of technical terms.
- Add timing logs around bundle DB reads if any slow queries remain.

If you want, I can add a short `docs/DEVELOPER_NOTES.md` entry with commands to run a quick local timing test and sample log lines to watch. Let me know which of the optional steps to take.
