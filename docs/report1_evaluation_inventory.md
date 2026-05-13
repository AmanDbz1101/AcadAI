# AcadAI Report Inventory

## 1. Chapter 6 Full Section List

Chapter 6 starts at [reports/report1.tex](reports/report1.tex#L2362). There is no section in the current file titled Evaluation Dataset Construction; the matching current section 6.4 is Evaluation Approach for Retrieval and Answer Quality.

Testing and Evaluation; label: ch:testing; status: substantial.
Testing Strategy; label: none; status: substantial. Subsections: Unit Testing, Integration Testing, Manual Testing, Pipeline and End-to-End Smoke Tests.
Test Cases; label: none; status: substantial. Subsections: Validation of Valid and Invalid PDFs, Corrupted and Encrypted PDF Handling, Text Extraction Correctness, Section Hierarchy Correctness, Database Persistence Checks, Retrieval and QA Checks.
Evaluation Metrics; label: none; status: substantial. Subsections: Extraction Accuracy, Coverage of Metadata Fields, Hierarchy Quality, Retrieval Relevance, Response Usefulness, Processing Time.
Evaluation Approach for Retrieval and Answer Quality; label: none; status: substantial. Subsections: Retrieval Quality Metrics, Answer Quality Metrics, Retrieval-Generation Alignment, Ablation Study Design.
Error Analysis; label: sec:error_analysis; status: substantial. Subsections: Scanned PDFs, Complex Tables and Figures, Non-Standard Section Numbering, Rotated and Low-Contrast Pages, Silent Error Handling.
Chapter Summary; label: none; status: substantial.

## 2. Section 6.4 Full Text

The current Section 6.4 text, with all subsections, is below. This is the current section that exists in the file; it is not titled Evaluation Dataset Construction.

```latex
\section{Evaluation Approach for Retrieval and Answer Quality}
% ------------------------------------------------------------

Evaluation is conducted on a manually annotated dataset of question-answer-section
triplets constructed from three CS research papers: one Theory paper, one Applied
paper, one Survey paper, corresponding to the three categories produced by the
classifier. For each paper, 15--17 questions are written per paper, yielding 50
total QA pairs. Each entry contains the question text, a 2--4 sentence reference
answer written from the section text, a list of relevant chunk identifiers, and a
question type label (factual, conceptual, or comparative). No automated question
generation is used for the evaluation dataset; all questions and reference answers
are manually authored to ensure quality ground truth.

Retrieval quality metrics are computed by running each question through the
retrieval pipeline and comparing returned chunk identifiers against the annotated
relevant chunk identifiers. Answer quality metrics are computed using the RAGAS
framework~\cite{es2023ragas}, which uses an LLM judge to score faithfulness and
answer relevancy without requiring human scoring of every response. An ablation
study across three retrieval configurations provides quantitative evidence for
the contribution of each pipeline component.

\subsection{Retrieval Quality Metrics}

\textbf{Precision@5:} The fraction of top-5 retrieved chunks that appear in the
annotated relevant chunk set, averaged across all 50 questions. This measures
the signal-to-noise ratio of retrieval.

\begin{equation}
\text{Precision@5} = \frac{1}{|Q|} \sum_{q \in Q}
\frac{|\text{Retrieved}_5(q) \cap \text{Relevant}(q)|}{5}
\end{equation}

\textbf{Recall@5:} The fraction of all annotated relevant chunks that appear in
the top-5 retrieved results, averaged across all 50 questions. This measures
retrieval completeness.

\begin{equation}
\text{Recall@5} = \frac{1}{|Q|} \sum_{q \in Q}
\frac{|\text{Retrieved}_5(q) \cap \text{Relevant}(q)|}{|\text{Relevant}(q)|}
\end{equation}

\textbf{Mean Reciprocal Rank (MRR):} The average of $1/r$ where $r$ is the rank
of the first relevant chunk in the retrieved list. MRR rewards systems that
place the correct chunk at rank 1 rather than rank 5.

\begin{equation}
\text{MRR} = \frac{1}{|Q|} \sum_{q \in Q} \frac{1}{r_q}
\end{equation}

\subsection{Answer Quality Metrics}

Answer quality is evaluated using the RAGAS framework with
\texttt{llama-3.3-70b-versatile} as the judge model.

\textbf{Faithfulness:} Measures the degree to which every claim in the generated
answer is supported by the retrieved chunks. A score of 1.0 indicates complete
grounding; lower scores indicate hallucination. A faithfulness mean above 0.70
across the 50 questions is taken as the passing threshold for the current system.

\textbf{Answer Relevancy:} Measures how directly the generated answer addresses
the question asked. Evaluated independently of faithfulness to separate the
grounding problem from the relevance problem.

\textbf{Context Precision:} Measures whether the retrieved chunks that were
actually useful for answering the question appear higher in the ranked list than
irrelevant chunks.

\subsection{Retrieval-Generation Alignment}

To verify that answers are grounded in retrieved content rather than the model's
parametric knowledge, a context entailment check is performed per answer: the
judge LLM determines whether the answer could be derived solely from the
retrieved chunks without access to any other information. This provides a binary
faithfulness signal complementary to the RAGAS faithfulness score.

\subsection{Ablation Study Design}

The same 50 questions are evaluated under three configurations to quantify the
contribution of each retrieval component:

\begin{table}[h]
\centering
\begin{tabular}{lcccc}
\toprule
\textbf{Configuration} & \textbf{Dense} & \textbf{BM25} &
\textbf{Reranker} & \textbf{Section Filter} \\
\midrule
Baseline (dense only)  & \checkmark & --         & --         & -- \\
Hybrid (no reranker)   & \checkmark & \checkmark & --         & -- \\
Full system            & \checkmark & \checkmark & \checkmark & \checkmark \\
\bottomrule
\end{tabular}
\caption{Ablation study configurations}
\label{tab:ablation}
\end{table}

Precision@5 and MRR are computed for each configuration. The improvement from
baseline to full system demonstrates the cumulative value of each added
component.
```

## 3. Section 6.3 Metrics Table

```latex
\begin{table}[ht]
\centering
\caption{Evaluation metric results}
\label{tab:metrics}
\begin{tabular}{llll}
\toprule
\textbf{Metric} & \textbf{Status} & \textbf{Value} & \textbf{Target} \\
\midrule
Retrieval Precision@5     & Measured & 0.50\ (50\%)    & $\geq 0.50$ \\
Retrieval Recall@5        & Measured & 0.92\ (92\%)    & $\geq 0.80$ \\
Answer Faithfulness       & Measured & 0.835\ (83.5\%) & $\geq 0.80$ \\
Answer Relevancy          & Measured & 0.886\ (88.6\%) & $\geq 0.80$ \\
Code Coverage             & Measured & 75\%            & $\geq 70\%$ \\
Test Pass Rate            & Measured & 89\%\ (73/82)   & $\geq 85\%$ \\
Processing Time (per PDF) & Partial  & 2--5 seconds    & $\leq 10$\,s \\
\bottomrule
\end{tabular}
\end{table}
```

## 4. Chapter 7 Full Section List

Chapter 7 starts at [reports/report1.tex](reports/report1.tex#L2748).

Results and Discussion; label: none; status: substantial.
Paper Type Classification Results; label: none; status: substantial.
Retrieval Evaluation Results; label: none; status: substantial.
Answer Quality Evaluation Results; label: none; status: substantial.
Ablation Study Results; label: none; status: substantial.
System Output and Web Interface Results; label: none; status: substantial. Subsection: Web Interface and Guide Generation.
Discussion; label: none; status: substantial. Subsections: Classification, Retrieval, Answer Quality and Architectural Validity.
Chapter Summary; label: none; status: substantial.

## 5. Chapter 7 Retrieval Table

```latex
\begin{table}[h]
\centering
\begin{tabular}{lccc}
\toprule
\textbf{Category} & \textbf{Precision@5} & \textbf{Recall@5} & \textbf{MRR} \\
\midrule
\multicolumn{4}{l}{\textit{By paper type}} \\
Applied     & 0.34 & 0.66 & 0.54 \\
Survey      & 0.29 & 0.54 & 0.65 \\
Theory      & 0.35 & 0.57 & 0.58 \\
\midrule
\multicolumn{4}{l}{\textit{By question type}} \\
Factual     & 0.33 & 0.61 & 0.58 \\
Conceptual  & 0.36 & 0.69 & 0.65 \\
Comparative & 0.23 & 0.45 & 0.55 \\
\midrule
\multicolumn{4}{l}{\textit{Overall}} \\
\textbf{Full evaluation set} & \textbf{0.33} & \textbf{0.59} & \textbf{0.59} \\
\bottomrule
\end{tabular}
\caption{Retrieval evaluation results across paper types and question types
(44 annotated QA pairs)}
\label{tab:retrieval_results}
\end{table}
```

## 6. Chapter 7 RAGAS Table

```latex
\begin{table}[h]
\centering
\begin{tabular}{lcc}
\toprule
\textbf{Metric} & \textbf{Score} \\
\midrule
Faithfulness      & 0.74  \\
Answer Relevancy  & 0.67  \\
Context Precision & 0.57  \\
\bottomrule
\end{tabular}
\caption{RAGAS answer quality evaluation scores}
\label{tab:ragas_results}
\end{table}
```

## 7. Chapter 7 Discussion Subsections

```latex
\subsection*{Retrieval}
The retrieval evaluation results support the core architectural hypothesis of
this project. An MRR of 0.59 indicates that the first relevant chunk
consistently appears within the top two retrieved results, confirming that the
section-scoped hybrid pipeline surfaces relevant content near the top of the
ranked list. The ablation study provides the strongest evidence for the
architectural choices made. Each added component contributes measurable gain,
with the cumulative improvement from the dense-only baseline to the full system
reaching 0.15 in Precision@5 and 0.21 in MRR. This directly demonstrates that
BM25, cross-encoder reranking, and section-scoped filtering are not decorative
additions. Each one earns its place in the pipeline.

Context precision of 0.52 is the weakest result and is expected given the
retrieval Precision@5 of 0.33. Some irrelevant chunks are reaching the answer
generation step, and this is the primary target for improvement through chunk
size reduction and relevance threshold calibration in subsequent iterations.

\subsection*{Answer Quality and Architectural Validity}
The RAGAS faithfulness score of 0.74 is the most significant result in the
entire evaluation. It confirms that generated answers are grounded in retrieved
content rather than the language model's parametric knowledge. A system that
scores high on faithfulness is not a document injection wrapper. It is
constrained by what the retriever returns, and the retriever is constrained by
the section being read. This provides empirical evidence for the central design
decision of this project: the deliberate decoupling of guide generation from
answer generation, where guide generation uses only the title, abstract, and
classification output, and answer generation uses only the retrieved chunks from
the active section. The faithfulness score validates that this separation is
working as intended.
```

## 8. Chapter 8 Conclusion Metrics Paragraph

```latex
The paper type classifier achieves 98.14\% accuracy on a 429-paper held-out test
set, confirming that lightweight TF-IDF features are sufficient for reliable
paper categorisation. The hybrid retrieval pipeline achieves a Mean Reciprocal
Rank of 0.59 and Precision@5 of 0.33 on a manually annotated 44-question
evaluation dataset, with the ablation study demonstrating that each pipeline
component contributes measurable improvement over the dense-only baseline.
Answer quality evaluation using the RAGAS framework yields a faithfulness score
of 0.74, providing empirical confirmation that the system grounds its answers in
retrieved evidence rather than parametric knowledge.
```

## 9. Abstract Metrics

The abstract does not currently mention any metric values, so there is nothing metric-specific to paste from it.

## 10. Evaluation Artifact File Names

- Original QA pairs file: [backend/evaluation/dataset/qa_pairs.json](backend/evaluation/dataset/qa_pairs.json)
- Separate 40-question QA pairs file: not found in the workspace
- Retrieval results JSON: [backend/evaluation/results/retrieval_results.json](backend/evaluation/results/retrieval_results.json)
- Separate retrieval JSON for 40 questions: not found in the workspace
- Answer results JSON: [backend/evaluation/results/answer_results.json](backend/evaluation/results/answer_results.json)
- Other result file present: [backend/evaluation/results/generated_answers.json](backend/evaluation/results/generated_answers.json)
- Combined or merged evaluation output files: none found by name in the workspace
- Full report MD file: [docs/RETRIEVAL_SYSTEM_FULL_REPORT_2026-03-29.md](docs/RETRIEVAL_SYSTEM_FULL_REPORT_2026-03-29.md)

Two naming mismatches are worth correcting before you insert anything: the current Chapter 6 Section 6.4 is titled Evaluation Approach for Retrieval and Answer Quality, and the current Chapter 7 / Chapter 8 evaluation text uses 44-question wording, not 32-question wording.