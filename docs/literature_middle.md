\section{PDF Extraction and OCR}
% ------------------------------------------------------------

Research documents are predominantly distributed in the Portable 
Document Format (PDF), which presents significant challenges for 
automated text extraction. Unlike plain text formats, PDF encodes 
content as a stream of graphical operators rather than semantic 
text units, meaning the logical reading order, paragraph boundaries, 
and structural elements must be reconstructed algorithmically 
\cite{pdfminer2023}.

\subsection{Text-Based PDF Extraction}

For digitally authored PDFs, text extraction tools operate directly 
on the embedded character streams. Tools such as PDFMiner 
\cite{pdfminer2023}, PyMuPDF \cite{pymupdf2023}, and pdfplumber 
\cite{pdfplumber2023} retrieve character-level glyphs along with 
positional metadata including bounding box coordinates, font size, 
and font weight. These positional attributes are critical for 
downstream tasks such as heading detection and column 
disambiguation in multi-column academic layouts.

However, raw character extraction is insufficient for academic 
document understanding. Research papers typically contain complex 
layouts with two-column formats, mathematical equations, figures, 
tables, and footnotes interspersed with body text. Nave 
concatenation of extracted characters produces malformed text 
that corrupts downstream NLP tasks \cite{vila2021}. This problem 
motivated the development of layout-aware extraction frameworks.

Document layout analysis approaches the problem as a computer 
vision task, treating page images as inputs and identifying 
semantic regions such as titles, paragraphs, figures, and tables 
using object detection models.Layoutparser \cite{shen2021} 
introduced a unified framework combining layout detection with 
downstream text extraction. Building on this line of work, 
Docling \cite{docling2024} extends layout-aware extraction with 
a full document understanding pipeline. Docling applies a 
TableFormer model \cite{nassar2022} for structured table 
reconstruction and a dedicated layout model for region 
classification, producing a rich hierarchical document 
representation that preserves reading order, table cell 
structure, figure boundaries, and provenance metadata including 
per-element page numbers and bounding box coordinates.

The provenance data exposed by Docling, specifically the 
\texttt{prov} attribute on each document item containing 
\texttt{page\_no} and \texttt{bbox} fields, enables fine-grained 
location tracking of every extracted text element. This 
capability is particularly valuable for citation-level navigation 
in reading assistance systems, where retrieved text chunks must 
be mappable back to specific page regions in the original document.

% After explaining layout-aware extraction, before OCR subsection
\begin{figure}[h]
    \centering
    \includegraphics[width=0.85\textwidth]{figures/docling_pipeline.png}
    \caption{Docling document understanding pipeline showing layout 
    detection, table structure recognition, and provenance extraction 
    stages for a two-column academic PDF.}
    \label{fig:docling_pipeline}
\end{figure}

\subsection{Scanned PDFs and OCR}

A significant proportion of academic documents, particularly 
older publications and conference proceedings, exist as scanned 
image PDFs with no embedded text layer. Optical Character 
Recognition (OCR) is required to recover textual content from 
these documents. Traditional OCR engines such as Tesseract 
\cite{smith2007} apply image binarisation, line segmentation, 
and character classification pipelines to produce text output, 
though accuracy degrades substantially on low-resolution scans, 
two-column layouts, and mathematical notation.

Deep learning approaches have substantially advanced OCR 
accuracy. PaddleOCR \cite{du2020} applies a detection-then-recognition 
pipeline using differentiable binarisation for text region 
detection and a scene text recognition model for character 
transcription, achieving competitive performance on document 
benchmarks. EasyOCR \cite{easyocr2021} similarly applies a 
two-stage deep learning architecture and supports over eighty 
languages with a straightforward Python interface.

Docling integrates multiple OCR backends including Tesseract, 
EasyOCR, and RapidOCR as interchangeable engines, applying them 
selectively on pages with low text density detected during the 
initial conversion pass. This hybrid strategy, processing 
digitally authored pages with the native text layer while 
falling back to OCR for image-heavy or scanned pages, optimises 
both accuracy and throughput for heterogeneous document 
collections.

\subsection{GPU Acceleration}

Modern document understanding pipelines apply neural models for 
layout detection, table structure recognition, and OCR, each 
requiring significant computation per page. GPU acceleration 
is therefore essential for acceptable throughput in interactive 
systems. Docling exposes a configurable accelerator device 
parameter that routes tensor operations to CUDA-enabled GPUs 
when available \cite{docling2024}. For a typical thirty-page 
academic paper, GPU-accelerated conversion completes in 
approximately seventeen to nineteen seconds compared to 
several minutes on CPU, making real-time upload processing 
feasible.

% ------------------------------------------------------------
\section{Metadata Extraction}
% ------------------------------------------------------------

Structured metadata extraction from academic papers encompasses 
the identification of bibliographic fields including title, 
authors, abstract, keywords, section headings, and citation 
references. Accurate metadata extraction underpins document 
indexing, retrieval, categorisation, and reading guide 
generation.

\subsection{Heuristic and Rule-Based Approaches}

Early metadata extraction systems applied hand-crafted rules 
exploiting typographic conventions in academic publishing. 
Titles typically appear as the largest font on the first page, 
abstracts follow a labelled heading, and author affiliations 
appear in smaller font between the title and abstract. 
Systems such as ParsCit \cite{councill2008} applied 
conditional random fields trained on positional and 
typographic features to extract citations and header fields 
from research papers.

GROBID \cite{lopez2009} advanced this approach by applying 
a cascade of sequence labelling models to segment and label 
document zones at multiple granularities, from document-level 
header fields down to individual citation components. GROBID 
remains a widely used baseline for academic metadata extraction, 
particularly for citation parsing, though its accuracy on 
non-standard layouts and documents from non-Western publishers 
is limited \cite{tkaczyk2018}.

\subsection{LLM-Assisted Extraction}

Large language models have emerged as a powerful alternative 
to rule-based metadata extraction, particularly for fields 
requiring semantic understanding rather than positional 
heuristics. Prompting an LLM with the first page text of a 
document and requesting structured field extraction leverages 
the model's understanding of academic writing conventions to 
identify title, abstract, and author fields even in 
non-standard layouts \cite{wei2022}.

The approach is particularly effective when combined with 
structured output constraints. Using JSON schema-constrained 
generation, LLMs can be prompted to return metadata as a 
typed dictionary with explicit field names, enabling 
programmatic consumption of extracted values without fragile 
string parsing \cite{openai2023}. Confidence scoring can be 
derived from field coverage, where the proportion of 
successfully extracted non-null fields indicates extraction 
quality.

A practical hybrid strategy applies layout-based extraction 
as the primary path, using heading detection to identify the 
abstract region and section names from the document structure, 
and reserves LLM-based extraction as a fallback for documents 
where the primary path achieves insufficient field coverage. 
This combination achieves near-complete metadata coverage 
across diverse document types while minimising LLM API calls 
for well-structured documents \cite{docling2024}.

\subsection{Section Heading Extraction}

Section heading identification is a prerequisite for both 
metadata extraction and document chunking. Headings are 
characterised by elevated font size, bold weight, or 
numbered prefix patterns such as Arabic numerals, Roman 
numerals, or alphabetic labels. Vila et al. \cite{vila2021} 
demonstrated that token-level classification combining 
textual and positional features substantially outperforms 
purely positional heuristics for heading detection in 
scientific documents.

Docling exposes extracted headings with their hierarchical 
level inferred from font size and numbering depth, providing 
a structured list of section titles with associated page 
numbers that forms the input to section hierarchy detection.

% ------------------------------------------------------------
\section{Section Detection and Hierarchy Extraction}
% ------------------------------------------------------------

The logical structure of an academic paper is organised as a 
hierarchy of sections, subsections, and nested content. 
Recovering this hierarchy from extracted text is essential 
for reading comprehension support, targeted retrieval, and 
coherent chunking, as section boundaries define the natural 
semantic units of a research document.

\subsection{Why Section Hierarchy Matters}

Reading comprehension research has long established that 
hierarchical document structure supports comprehension by 
providing readers with a mental map of content organisation 
\cite{kintsch1978}. A three-pass reading strategy, in which 
readers first survey section titles and abstracts, then read 
methodology and results sections in depth, and finally 
synthesise conclusions, is a widely recommended approach for 
efficiently extracting understanding from dense research papers 
\cite{keshav2007}. Automated reading guides that follow this 
strategy must therefore ground their instructions in the 
actual section hierarchy of the target document.

For information retrieval, section-aware chunking produces 
chunks that respect semantic boundaries rather than splitting 
content arbitrarily at fixed token counts. Retrieval systems 
that filter by section allow users to direct questions at 
specific document regions, improving precision when the user 
already has structural knowledge of the paper. Formal 
evaluation of section-aware retrieval has demonstrated 
improved answer relevance compared to section-agnostic 
chunking on scientific QA benchmarks \cite{yang2023}.

\subsection{Section Segmentation Approaches}

Section segmentation can be approached as a sequence 
labelling task, a classification problem at the text block 
level, or a rule-based post-processing step applied to 
layout-extracted headings.

Rule-based approaches exploit numbering conventions and 
font-weight signals. A section heading numbered \texttt{3.2} 
is unambiguously a level-two subsection under section three. 
Regular expression matching on common academic numbering 
patterns combined with font size thresholding provides a 
reliable baseline for well-formatted papers \cite{mao2012}.

Machine learning approaches treat section boundary detection 
as a binary classification task at each text block, using 
features including relative font size, vertical position, 
line spacing, and preceding content. DocBank \cite{li2020} 
provides a large-scale benchmark of annotated academic 
document structures that has been used to train layout 
classification models. SciPDF Parser and similar tools 
apply trained models to assign semantic labels including 
title, abstract, section heading, paragraph, figure caption, 
and table to each extracted text block.

\subsection{Hierarchy Tree Construction}

Once section headings are identified with their associated 
heading levels, a section hierarchy tree is constructed by 
interpreting level assignments as parent-child relationships. 
A level-one heading opens a new top-level section; a 
subsequent level-two heading becomes a child of the most 
recently opened level-one section. This stack-based 
construction algorithm is robust to typical academic 
numbering schemes.

Practical challenges in hierarchy construction include 
inconsistent heading level assignment by layout models, 
unnumbered sections such as Abstract and Acknowledgements 
that must be inferred from position and content, and 
appendices that follow the main body with separate numbering. 
Post-processing heuristics normalise these cases by 
assigning unnumbered headings to the appropriate level based 
on positional context and known heading vocabulary.

The output of section hierarchy extraction is a structured 
tree where each node carries the section title, inferred 
heading level, page number of first occurrence, and 
references to child sections. This tree is serialised as a 
JSON artifact that serves as the primary input to the 
document chunking pipeline, ensuring that chunk boundaries 
align with semantic section boundaries rather than arbitrary 
token counts.

\subsection{Confidence and Coverage Metrics}

Evaluating the quality of extracted section hierarchies 
requires comparing detected sections against ground truth 
annotations. In the absence of ground truth for a given 
document, proxy metrics such as heading count, maximum 
detected depth, and coverage of known section vocabulary 
(Introduction, Related Work, Methodology, Experiments, 
Conclusion) provide a confidence estimate. A high confidence 
score indicates that the extracted hierarchy is likely 
complete and correctly structured, while a low score 
triggers fallback handling such as coarser chunking or 
guide generation with reduced section specificity.