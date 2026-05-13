# AcadAI Report — Full Analysis, To-Do List, and Section Evaluation

---

## PART 1 — CRITICAL FINDING: THE CORRECTIONS WERE NEVER APPLIED

Everything we fixed in the last three conversations was written into separate
`.tex` files but **was never merged into the main document you just submitted**.
The document you uploaded still contains every wrong number. This is the most
urgent thing to fix before anything else.

### Metric corrections that must be made RIGHT NOW

| Location in document | Current (wrong) | Correct |
|---|---|---|
| Ch6 §6.3 metrics table — Precision@5 | 0.50 (50%) | **0.30 (30%)** |
| Ch6 §6.3 metrics table — Recall@5 | 0.92 (92%) | **0.9375 (93.8%)** |
| Ch6 §6.3 metrics table — Processing time | 2–5 s only | **2–5 s extraction / 22.27 s full pipeline** |
| Ch6 §6.3 prose — "Precision@5 of 0.50" | 0.50 | **0.30** |
| Ch6 §6.3 prose — "Recall@5 of 0.92" | 0.92 | **0.9375** |
| Ch6 §6.4 ablation design table | "same 50 questions" | **32 questions** |
| Ch6 §6.3 opening paragraph | no 32 vs 44 explanation | **add explanation** |
| Ch6 §6.4 Error Analysis | generic 4 subsections | **add iterative cleanup story** |
| Ch7 retrieval table caption | "44 annotated QA pairs" | **32 annotated questions** |
| Ch7 retrieval table — Overall row P@5 | 0.33 | **0.30** |
| Ch7 retrieval table — Overall row R@5 | 0.59 | **0.9375** |
| Ch7 RAGAS table — Faithfulness | 0.74 | **0.835** |
| Ch7 RAGAS table — Answer Relevancy | 0.67 | **0.886** |
| Ch7 RAGAS prose | "0.74 indicates majority…" | update to **0.835** |
| Ch7 ablation prose | "same 44 questions" | **32 questions** |
| Ch7 ablation full-system row P@5 | 0.33 | **0.30** |
| Ch7 ablation cumulative gain prose | "+0.15 in Precision@5" | **+0.12** |
| Ch7 Discussion — "faithfulness score of 0.74" | 0.74 | **0.835** |
| Ch7 Discussion — "Context precision of 0.52" | 0.52 | **0.57** (table says 0.57, prose says 0.52 — internal mismatch) |
| Ch7 Chapter Summary — "faithfulness score of 0.74" | 0.74 | **0.835** |
| Ch8 Conclusion — "faithfulness score of 0.74" | 0.74 | **0.835** |
| Ch8 Conclusion — "44-question evaluation dataset" | 44 | **32** |
| Ch8 Conclusion — "Precision@5 of 0.33" | 0.33 | **0.30** |

---

## PART 2 — STRUCTURAL BUGS (will break LaTeX or confuse the examiner)

### Bug 1 — Two Chapter 4s
You have `\chapter{System Design}` and `\chapter{Implementation}` both numbered
as Chapter 4. LaTeX will render both as "4." because the counter resets. The
examiner's printed copy will show two chapters both called "Chapter 4."

**Fix:** This is not something you fix manually. LaTeX auto-numbers `\chapter`
commands. The current document has System Design as Chapter 4 and Implementation
immediately after. LaTeX will call them 4 and 5 automatically — but your Table
of Contents and any cross-references using `\ref{ch:system-design}` must be
checked.

### Bug 2 — Duplicate bibliography entry
`\bibitem{keshav2007}` appears twice in the bibliography. LaTeX will throw a
warning and citation behaviour will be unpredictable.

**Fix:** Delete one of them (keep the ACM SIGCOMM one, it is more complete).

### Bug 3 — MIN_RELEVANCE_THRESHOLD contradiction
- Chapter 3 states: `MIN_RELEVANCE_THRESHOLD = 0.35`
- Chapter 4 states: `threshold of 0.35`
- The evaluation cleanup story (which we wrote) states it was **raised to 0.50**

One of these is the current production value. You must pick one and use it
everywhere. If the threshold was raised to 0.50 as part of the cleanup, then
every place that says 0.35 is wrong and reflects an earlier version of the
system.

### Bug 4 — Internal mismatch in context precision
Chapter 7 Discussion prose says "Context precision of **0.52**" but the RAGAS
table directly above shows **0.57**. The reader sees two different numbers for
the same metric on the same page.

---

## PART 3 — INCOMPLETE SECTIONS (TBD markers still present)

These sections exist in the document as empty shells or commented-out
placeholders. An examiner reading a printed copy will see blank pages.

| Section | Status | Priority |
|---|---|---|
| Ch2 §2.5 — Workflow Orchestration and LangGraph | **Empty** (% TBD comment) | **Critical** — LangGraph is a core system technology |
| Ch3 §3.7 — Development Approach | **Empty** (% TBD comment) | Medium |
| Ch4 — Use case diagram | Commented out | High — examiners look for this |
| Ch4 — Architecture block diagram | Commented out | High |
| Ch4 — Sequence diagram (indexing) | Commented out | High |
| Ch4 — Sequence diagram (query) | Commented out | High |
| Appendix A — API Endpoint Reference | Empty | Low |
| Appendix B — Database Schema | Empty | Medium |
| Appendix C — Example JSON Outputs | Empty | Low |
| Appendix D — Additional Figures | Empty | Low |

---

## PART 4 — MISSING FIGURES (will cause LaTeX compilation errors)

Every `\includegraphics` call below refers to a file that must exist on disk
at the path specified, relative to the `.tex` file.

| Filename in code | Issue |
|---|---|
| `logo.png` | Must exist |
| `schemanticscholar.png` | **Misspelled** — should be `semanticscholar.png` (or fix the filename) |
| `explainpaper.png` | Must exist |
| `figures/docling_pipeline.png` | Must exist at `figures/` subdirectory |
| `rag.png` | Must exist |
| `hybrid_rag.png` | Must exist |
| `offline_indexing_phase.jpg` | Must exist |
| `online_query_phase.jpg` | Must exist |
| `ui_screenshot.png` | Must exist |
| `paper_list.png` | Added in Ch7 rewrite — must exist |
| `reading_guide.png` | Added in Ch7 rewrite — must exist |
| `qa_panel.png` | Added in Ch7 rewrite — must exist |

---

## PART 5 — SECTION-BY-SECTION QUALITY EVALUATION

### Abstract — Grade: C
**Problems:** No numbers at all. An abstract for an evaluated system project
should contain at least the headline metrics. An examiner reads the abstract
first and decides the quality of the work from it. Currently it reads like a
product description, not a research report abstract.

**What to add:** One sentence with the three key results: classifier accuracy,
retrieval MRR, and faithfulness score.

---

### Chapter 1 Introduction — Grade: B+
**Good:** Problem statement is clear, objectives are specific and measurable,
scope is well-defined with explicit out-of-scope items.

**Minor issue:** The opening paragraph runs the first two sentences together
with `\\` instead of a blank line. Not a LaTeX error but poor typographic
practice.

---

### Chapter 2 Literature Review — Grade: B−
**Good:** PDF extraction, metadata extraction, and section detection subsections
are detailed and well-cited.

**Critical gap:** §2.5 (Workflow Orchestration and LangGraph) is **empty**.
LangGraph is what makes your system different from a simple chain of function
calls. An examiner who asks "why LangGraph instead of LangChain?" will have
nothing to read. You need at minimum 300–400 words here explaining what
LangGraph is, what a StateGraph is, and why state-machine-based orchestration
matters for a multi-step document processing pipeline.

**Minor gap:** The gap analysis mentions "content-type-aware chunking" as a
novel contribution but the literature review does not survey any work on
chunking strategies. There is no subsection explaining why fixed-token chunking
is inferior and why content-type separation matters. If you claim this as a
contribution, the literature review should set it up.

---

### Chapter 3 Requirements and Methodology — Grade: B
**Good:** The two-phase architecture description is clear. The content-type-aware
chunking methodology is well explained.

**Problems:**
- §3.4 Evaluation Approach states "50 total QA pairs" and "averaged across all
  50 questions" — both wrong. Must be updated to the 32/44 split with explanation.
- §3.7 Development Approach is **empty**.
- The hybrid retrieval parameters (top-100 candidates, RRF k=60, threshold 0.35
  or 0.50) appear in three places (Ch3, Ch4, and Ch6) with slight variations.
  These must all agree.

---

### Chapter 4 System Design — Grade: B−
**Good:** The module descriptions are clear. The database schema subsections
are useful even if high-level.

**Critical problem:** All four system diagrams are commented out. A system
design chapter without diagrams fails its primary purpose. An examiner reading
this chapter will see four captions with no figures. This looks unfinished
because it is unfinished.

If you cannot produce polished vector diagrams, even rough block diagrams made
in draw.io and exported as PNG are better than empty figure environments.

---

### Chapter 5 Implementation — Grade: B+
**Good:** Technical depth is appropriate. The six-stage retrieval pipeline is
clearly documented with stage names and parameters. The content-type chunking
description is detailed.

**Minor issues:** The threshold stated here (0.35) may conflict with the
corrected value (0.50). Check and fix.

---

### Chapter 6 Testing and Evaluation — Grade: D (due to wrong numbers)
The structure is good. The test case table is good. The evaluation approach
methodology is solid.

**But all the actual metric values are wrong** and they are the wrong values
from before the corrections we worked through together. Until the numbers are
fixed this chapter directly contradicts your own saved evaluation artefacts.

Also missing: the 32/44 explanation paragraph, the iterative cleanup story in
§6.4 (which we wrote), and the processing time split.

---

### Chapter 7 Results and Discussion — Grade: D (due to wrong numbers)
Same problem as Chapter 6 — all metric values are the old wrong set.

Additionally, the version of Chapter 7 you uploaded is the original version,
not the rewrite we produced. The rewrite had extraction results, hierarchy
results, concrete QA examples, and the pipeline timing table. None of that is
here. This chapter is currently just four tables and a discussion.

**What is missing compared to the rewrite:**
- §7.1 Extraction Results (pipeline log, timing table, metadata table)
- §7.2 Hierarchy and Structure Results (schema table, hierarchy table)
- §7.3 Concrete QA examples (three worked examples)
- Additional screenshots (paper_list, reading_guide, qa_panel)

---

### Chapter 8 Conclusion — Grade: C
Structure is fine. Limitations are honest and appropriate.

**Problem:** All metric references are wrong (0.74, 44-question, 0.33). The
conclusion is the last thing an examiner reads. Sending them away with wrong
numbers is particularly bad.

---

## PART 6 — WHAT YOUR TEACHER WILL FOCUS ON MOST

Based on standard practice for a minor project examination at an engineering
college:

**1. Number consistency (highest scrutiny)**
Examiners cross-reference the same metric across the abstract, Chapter 6,
Chapter 7, and the conclusion. If any two of these disagree, the examiner
will ask about it directly. Currently they all disagree with each other and
all disagree with your own saved artefacts.

**2. Evaluation methodology (high scrutiny)**
"Where did your 32 test questions come from? Who wrote them? Why 32 and not
50 or 100? Why do you have 44 RAGAS samples but only 32 retrieval questions?"
These are standard examiner questions. You need airtight answers in the text.

**3. The ablation study (high scrutiny)**
This is the strongest scientific contribution in the report. An examiner
interested in NLP will read this carefully. The numbers and narrative here
must be completely consistent and the claim that "each component earns its
place" must be supported by the actual numbers (which it is, once corrected).

**4. System diagrams (medium scrutiny)**
Four commented-out figures in Chapter 4 will be noticed immediately on a
printed copy.

**5. LangGraph section being empty (medium scrutiny)**
If an examiner asks "explain your orchestration layer" and finds an empty
section in the report, that is a problem in a viva.

---

## PART 7 — MASTER TO-DO LIST

### Priority 1 — Do these before anything else (report-breaking)

- [ ] Fix all 22 metric values listed in Part 1 of this document
- [ ] Fix the two-Chapter-4 numbering bug (verify LaTeX renders 4 and 5)
- [ ] Remove duplicate `\bibitem{keshav2007}`
- [ ] Fix `schemanticscholar.png` filename (or rename the file)
- [ ] Decide on MIN_RELEVANCE_THRESHOLD: 0.35 or 0.50, then fix all occurrences
- [ ] Fix context precision: 0.52 vs 0.57 — pick one and use it everywhere

### Priority 2 — Fix before submission (content gaps)

- [ ] Apply the Chapter 6 corrections from `chapters6_7_final.tex` (32/44
      explanation paragraph, full iterative cleanup story in §6.4)
- [ ] Apply the Chapter 7 rewrite from `chapters6_7_final.tex` (extraction
      results, hierarchy results, QA examples, updated screenshots)
- [ ] Update Chapter 8 Conclusion with correct metrics
- [ ] Update Abstract with headline metrics (classifier accuracy, MRR,
      faithfulness score)
- [ ] Write the LangGraph section in Chapter 2 (§2.5, minimum 300 words)
- [ ] Add processing time split to metrics table and Processing Time subsection

### Priority 3 — Important for examination quality

- [ ] Uncomment and produce the four system diagrams in Chapter 4 (use draw.io
      if needed, export as PNG)
- [ ] Write the Development Approach section in Chapter 3 (§3.7)
- [ ] Add chunking strategy subsection to literature review (why content-type
      separation matters)
- [ ] Verify all figure files exist on disk before final compilation

### Priority 4 — Good to have

- [ ] Write Appendix B (Database Schema — full table definitions)
- [ ] Write Appendix C (Example JSON outputs)
- [ ] Add paper_list.png, reading_guide.png, qa_panel.png screenshots to Chapter 7
- [ ] Write Appendix A (API endpoint reference)

---

## PART 8 — MOTIVATION

This is a legitimate, well-scoped, and technically sound semester project.
Here is why, stated plainly.

**You built something that does not exist as a standalone, open tool.** Semantic
Scholar finds papers. Explainpaper explains passages. ChatGPT answers questions
from context you paste manually. Not one of these tools does what AcadAI does:
takes a PDF, understands what kind of paper it is, generates a structured
reading plan specific to that paper type, and then answers questions grounded
only in the section you are currently reading. That combination — classifier +
type-conditioned guide + section-scoped RAG — is a coherent original design,
not a tutorial project.

**The ablation study is real research.** You did not just build a system and
say "it works." You built three versions of the retrieval pipeline, evaluated
all three on an annotated dataset, and quantified the contribution of every
component. Precision@5 going from 0.18 to 0.30, MRR going from 0.38 to 0.59 —
those are real, earned numbers from real evaluation work. Most commercial
products ship without an ablation study. You did one.

**The evaluation cleanup story is evidence of engineering maturity.** You found
that your initial results were being distorted by labelling errors, noisy
chunks, wrong section mappings, and a bimodal reranker. You diagnosed each
problem, applied a targeted fix, and re-ran evaluation. That is exactly what
a professional ML engineer does. The fact that your Precision@5 is 0.30 and
not 0.80 does not mean the system is bad — it means you measured it honestly
after removing the things that were inflating it artificially.

**The technology choices are defensible.** Qdrant, LangGraph, Docling, cross-encoder
reranking with RRF fusion — these are current production-grade tools used in
real RAG systems at companies like Cohere, Pinecone, and Weaviate. You did not
use toy libraries. You used the tools that practitioners use.

**What "current technology being ahead" actually means for your project.** Yes,
GPT-4o can answer questions about a paper if you paste the whole thing in. But
that approach costs money per query, has no section awareness, gives no
structural reading guidance, and provides no evidence for which part of the
paper the answer came from. AcadAI is not competing with GPT-4o. It is a
specific tool for a specific use case: a student sitting down with an unfamiliar
paper who wants structured guidance and verifiable answers. That is a real
problem and a real solution, regardless of what the frontier models can do if
you have API credits.

The report has real problems right now, almost all of them fixable in a few
hours of careful editing. The underlying project is solid. The numbers, once
corrected and made consistent, tell a good story. Fix the document and it will
represent the work accurately.