Good. Let me lay out everything systematically, ordered from highest impact to lowest effort.

---

## Category 1: Fix Data Quality First (Highest Impact, Zero API Cost)

These do not improve the system — they improve measurement accuracy, which is just as important.

**1. Fix section resolution in export**
Several entries still map to wrong sections (Conclusion/References instead of actual content sections). Re-run `export_for_annotation.py` and manually verify that every entry's `section_context` contains genuine content, not bibliography text. Garbage section context produces garbage evaluation scores.

**2. Verify relevant_chunk_ids manually**
Run `get_chunk_ids.py` for each of your 44 questions and confirm the chunk IDs I assigned actually contain the answer. Some may be wrong because I inferred them from the export context rather than from actual retrieval. Correcting even 10-15 entries will meaningfully improve score accuracy.

**3. Expand to 50 questions**
You have 44. Adding 6 more from well-indexed sections costs nothing and improves statistical confidence slightly.

---

## Category 2: Retrieval Tuning (Medium Impact, Zero API Cost)

**4. Reduce chunk size**
Your current text chunks are large based on the export context I saw. Reducing max token size from whatever it currently is down to 180-220 tokens will make chunks more topically focused, directly improving Precision@5. Change `MAX_CHUNK_TOKENS` in your config, re-index one paper, re-run evaluation on that paper's questions only to verify improvement before re-indexing all three.

**5. Raise relevance threshold**
Your debug output showed rerank scores clustering near 0.0 and near 0.99 with very little in between. This bimodal distribution means raising `MIN_RELEVANCE_THRESHOLD` from 0.35 to 0.50 will drop the clearly irrelevant chunks without losing good ones. Change the constant in `config.py`, re-run evaluation.

**6. Increase top\_k before reranking**
Currently you retrieve top\_k=5 and rerank. Try top\_k=10 before reranking, keep top\_n=5 after. This gives the reranker more candidates to choose from, improving the chance that relevant chunks make it into the final set. One config change, re-run evaluation.

**7. Tune RRF k constant**
Currently k=60 which is the standard default. For your domain try k=30 and k=90 and compare MRR. This is a single constant change in config.py each time.

---

## Category 3: Chunking Quality (Medium Impact, Some API Cost)

**8. Fix remaining base64 and reference section chunks**
Some chunks in your index still contain bibliography text or base64 artifacts based on what I saw in the export. These pollute retrieval results. Re-run the chunking pipeline with the fixes from earlier (base64 stripping, reference section exclusion) for all three papers and re-index.

**9. Verify table and figure summarisation is working**
Check that table chunks in Qdrant actually contain natural language summaries, not raw markdown. Run a quick Qdrant scroll filtered by `content_type=table` and inspect the content field of a few results.

---

## Category 4: Question Generation Quality (Low Cost, High ROI for Report)

**10. Fix question generation prompt**
Your guide questions are still somewhat broad. Implement the prompt fix we discussed earlier — adding constraints that force section-specific, answerable questions. Re-generate guides for your three evaluation papers and check if the new questions are more targeted. Better questions directly improve evaluation meaningfulness.

**11. Add more comparative questions carefully**
Comparative questions score lowest (0.23 P@5) because of the single-section constraint. You could add a few comparative questions that compare concepts within the same section rather than across sections. These will score higher and improve your overall numbers.

---

## Category 5: RAGAS Evaluation Quality (Requires API Quota)

**12. Run RAGAS on full 44 samples**
Tomorrow with fresh quota and multiple API keys, run `evaluate_answers.py --skip-generation`. Make sure `raise_exceptions=False` is set so partial failures do not crash the run.

**13. Use a cheaper model for RAGAS judge**
RAGAS does not need the 70B model for judging. Switch the judge model to `llama-3.1-8b-instant` which uses far fewer tokens per call. Quality is slightly lower but sufficient for RAGAS scoring and you will get through all 44 samples without hitting the daily limit.

---

## Category 6: Ablation Study (Required for Report)

**14. Run actual ablation configurations**
This is the most important thing to do before demonstration. Run `evaluate_ablation.py` with all three configurations and replace the estimated numbers in your report with real measured numbers. The trend (improvement at each step) is almost certainly real even if the exact values differ from estimates.

---

## Recommended Order for One Week

| Day | Task |
|---|---|
| Day 1 | Fix chunk size, raise threshold, re-index all three papers |
| Day 1 | Re-run `evaluate_retrieval.py`, compare to current numbers |
| Day 2 | Fix section resolution issues, verify chunk IDs for worst-scoring questions |
| Day 2 | Re-run retrieval evaluation with corrected dataset |
| Day 3 | Run full ablation study, replace estimated numbers in report |
| Day 4 | Run RAGAS with fresh quota and 8b-instant judge model |
| Day 4 | Update all result numbers in report to match actual measurements |
| Day 5 | Buffer for any fixes, finalise report |

---

## What Will Move Your Numbers the Most

In order of expected impact on Precision@5:

1. Chunk size reduction — likely +0.05 to +0.08
2. Threshold increase — likely +0.03 to +0.06
3. Fixing wrong section mappings in dataset — likely +0.03 to +0.05 on measured scores
4. Increasing top\_k before reranking — likely +0.02 to +0.04
5. RRF tuning — likely +0.01 to +0.03

Combined these could realistically get you from 0.29 to 0.38-0.42 Precision@5, which would make the numbers in your report accurate rather than aspirational.