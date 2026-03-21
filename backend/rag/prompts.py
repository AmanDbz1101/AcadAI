"""
Research Paper Assistant - Prompts
===================================
All LLM prompts consolidated in one place.

Follows the Chat2Code pattern: simple functions returning formatted strings.
"""

from typing import Optional


def categorizer_prompt(title: str, abstract: str) -> str:
    """
    Generate the categorizer system prompt.

    Classifies research papers into 3 categories based on title and abstract.

    Args:
        title: Paper title
        abstract: Paper abstract

    Returns:
        Formatted prompt ready for LLM invocation
    """
    return f"""You are a research paper classification assistant.

Your task is to classify a research paper into EXACTLY ONE of the following three categories based ONLY on the provided title and abstract.

Categories:

1. THEORETICAL
Papers that formally prove or derive something: mathematical proofs, theorem/lemma statements, complexity analysis, formal methods, convergence analysis, algebraic or probabilistic derivations.

Strong signals:
- "we prove"
- "theorem"
- "lemma"
- "formally"
- "complexity"
- "convergence"
- mathematical derivations
- proof-based arguments

2. SURVEY
Papers that survey, review, or organize existing research. They do not propose a new method — they synthesize and categorize prior work.

Strong signals:
- "we survey"
- "we review"
- "comprehensive overview"
- "taxonomy"
- "X papers" (reviewing a large body of literature)
- literature review framing
- meta-analysis language

3. APPLIED
Default category. Use this for papers that propose, build, implement, or experimentally validate something — including original research, system design, benchmarks, datasets, and experimental studies.

Use APPLIED when neither THEORETICAL nor SURVEY signals are strong.

Typical signals:
- "we propose"
- "we introduce"
- "we implement"
- "we design"
- experimental results or benchmarks
- new dataset or evaluation framework
- system architecture or deployment

Classification rules:
- If the paper contains strong THEORETICAL signals ("we prove", "theorem", "lemma", "formally", "complexity", "convergence", mathematical derivations), classify as THEORETICAL.
- If the paper contains strong SURVEY signals ("we survey", "we review", "comprehensive overview", "taxonomy", references to reviewing many papers, literature review framing), classify as SURVEY.
- Otherwise, classify as APPLIED.
- The output must be EXACTLY one of: APPLIED, THEORETICAL, SURVEY — nothing else.

Instructions:
- Use ONLY the title and abstract.
- Choose the SINGLE most appropriate category.
- If multiple signals appear, classify according to the MAIN contribution.
- Do not guess beyond the information provided.

Return output strictly in the following JSON format:

{{
  "category": "<CATEGORY_NAME>",
  "confidence": "<HIGH | MEDIUM | LOW>",
  "reasoning": "<short explanation based on phrases or signals in the abstract>"
}}

Input:

Title: {title}

Abstract: {abstract}
"""


def retriever_prompt(query: str, category: str, sections_to_read: list = None) -> str:
    """
    Generate a retrieval query optimization prompt.
    
    Expands and enriches user queries for better vector search results.
    
    Args:
        query: Original user query
        category: Paper category (helps tailor query expansion)
        sections_to_read: Priority sections from the reading guide (for section-aware expansion)
        
    Returns:
        Formatted prompt for query expansion
    """
    section_hint = ""
    if sections_to_read:
        section_list = ", ".join(f'"{s}"' for s in sections_to_read[:6])
        section_hint = f"""
Priority Sections: {section_list}
When expanding the query, incorporate terminology and concepts likely to appear in these sections.
"""

    return f"""You are a semantic search query optimizer for academic papers.

Your task is to expand and enrich the user's query to improve retrieval from a vector database of research paper content.

Paper Category: {category}{section_hint}
User Query: {query}

Instructions:
- Identify key technical terms and concepts
- Add relevant synonyms and related terminology
- Consider section-specific language (e.g., "method", "results", "conclusion")
- If priority sections are listed, bias the expansion towards content found in those sections
- Keep the expanded query concise (1-3 sentences)
- Focus on semantic relevance, not keyword stuffing

Return only the optimized query, no explanations.
"""


def qa_prompt(query: str, context: str, metadata: dict) -> str:
    """
    Generate the Q&A prompt for answering questions about papers.
    
    Args:
        query: User's question
        context: Retrieved relevant content from vector store
        metadata: Paper metadata (title, category, etc.)
        
    Returns:
        Formatted prompt for question answering
    """
    title = metadata.get("paper_title", "Unknown Title")
    category = metadata.get("category", "APPLIED")
    
    return f"""You are an expert research assistant helping users understand academic papers.

Paper Title: {title}
Paper Type: {category}

User Question: {query}

Relevant Content:
{context}

Instructions:
- Answer the question directly and concisely
- Cite specific evidence from the provided content
- If the content doesn't contain enough information, say so
- Use academic language but keep it accessible
- For technical questions, explain key concepts briefly
- Include page/section references when available in metadata

Format your answer as:
1. Direct answer (2-3 sentences)
2. Supporting evidence with citations
3. Additional context if needed

Answer:"""


def summarizer_prompt(title: str, abstract: str, sections: list, category: str) -> str:
    """
    Generate the summarization prompt.
    
    Creates category-specific structured summaries.
    
    Args:
        title: Paper title
        abstract: Paper abstract
        sections: List of section dictionaries with titles and stats
        category: Paper category
        
    Returns:
        Formatted prompt for summary generation
    """
    section_list = "\n".join([f"- {s.get('title', 'Untitled')}" for s in sections[:10]])
    
    category_guidance = {
        "APPLIED": """
Focus on:
- Problem statement and motivation
- Proposed method, system, or dataset
- Key experimental results or benchmark findings
- Main contributions
- Limitations and future work
""",
        "THEORETICAL": """
Focus on:
- Main theoretical results (theorems/lemmas/proofs)
- Proof techniques and mathematical derivations
- Complexity analysis
- Assumptions and conditions
- Implications and applications
""",
        "SURVEY": """
Focus on:
- Scope of the survey
- Taxonomy or categorization scheme
- Key findings across reviewed papers
- Research gaps identified
- Future research directions
"""
    }

    guidance = category_guidance.get(category, category_guidance["APPLIED"])
    
    return f"""You are an expert research assistant creating structured paper summaries.

Paper Title: {title}

Abstract:
{abstract}

Paper Type: {category}

Section Structure:
{section_list}

{guidance}

Instructions:
- Create a comprehensive but concise summary (300-500 words)
- Structure by key aspects relevant to the paper type
- Extract 3-5 main contributions/findings
- Use clear, accessible academic language
- Highlight what makes this paper significant

Format:
## Summary
[Main summary paragraphs]

## Key Contributions
1. [First contribution]
2. [Second contribution]
...

## Significance
[Why this paper matters]

Generate the summary:"""


def reading_guide_prompt(title: str, abstract: str, sections: list, category: str) -> str:
    """
    Generate a Three-Pass reading guide for research papers.
    
    Args:
        title: Paper title
        abstract: Paper abstract
        sections: List of sections
        category: Paper category
        
    Returns:
        Formatted prompt for generating step-by-step reading guide
    """
    section_list = "\n".join([f"- {s.get('title', 'Untitled')}" for s in sections])
    
    return f"""You are an expert research assistant helping users read research papers efficiently.

Your task is to generate a step-by-step reading guide for this {category} paper using the Three-Pass Method.

Paper Title: {title}

Abstract:
{abstract}

Available Sections:
{section_list}

Three Pass Method Guidelines:

PASS 1 – Quick Scan (5–10 minutes)
Goal: Determine the main problem, contribution, and whether the paper is worth deeper reading.
Focus on high-level understanding.

PASS 2 – Understanding the Method (20–40 minutes)
Goal: Understand the core method and experimental setup without getting lost in details.

PASS 3 – Deep Analysis (1–2 hours)
Goal: Critically analyze the paper, understand technical details, and assess strengths and weaknesses.

Instructions for generating the guide:

1. Break each pass into multiple sequential steps.
2. Each step must clearly specify:
   - which section(s) to read
   - objective of reading
   - specific questions the reader should answer
   - expected output or insight
3. Adapt section references to the provided section list.
4. If a standard section is not present, suggest the closest alternative.
5. Mention figures/tables when relevant to understanding the method or results.
6. Keep instructions concise but actionable.

Return the guide in JSON format with structure:
{{
  "pass_1": [
    {{"section": "...", "objective": "...", "questions": ["..."], "expected_output": "..."}}
  ],
  "pass_2": [...],
  "pass_3": [...]
}}

Generate the reading guide:"""


def _flatten_sections(sections: list, level: int = 0) -> list:
    """Recursively flatten nested section structure."""
    result = []
    for section in sections:
        name = section.get('original_name', section.get('title', 'Untitled'))
        result.append(name)
        # Recursively process nested sections
        if 'sections' in section and section['sections']:
            result.extend(_flatten_sections(section['sections'], level + 1))
    return result


def applied_guide_prompt(
    title: str,
    abstract: str,
    introduction: str,
    conclusion: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0,
) -> str:
    """
    Generate a Three-Pass Method reading guide for APPLIED papers.

    Covers original research, system engineering, benchmark/dataset papers,
    and experimental papers — anything where authors built, implemented, or
    experimentally validated something.

    Args:
        title: Paper title
        abstract: Paper abstract
        introduction: Paper introduction text
        conclusion: Paper conclusion text
        sections: List of section dictionaries with original_name field
        num_figures: Number of figures in the paper
        num_tables: Number of tables in the paper

    Returns:
        Formatted prompt for generating an APPLIED paper reading guide
    """
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])

    return f"""You are an expert research assistant helping users read research papers efficiently.

Generate a step-by-step reading guide for this APPLIED paper using the Three-Pass Method.
This paper proposes, builds, implements, or experimentally validates something (original research, system design, benchmark, dataset, or experimental study).

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Introduction: {introduction}
- Conclusion: {conclusion}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

THREE PASS METHOD FOR APPLIED PAPERS:

PASS 1 – Quick Scan (5-10 min):
Reading order: Abstract → Conclusion → Figures/Tables → Introduction.
Goal: Understand the problem and whether the proposed solution works BEFORE reading how it works.
For each step, specify which sections to read, the objective, 2-3 questions to answer, and expected output.
If the paper has {num_figures} figures or {num_tables} tables, reference the most informative ones.

PASS 2 – Method Understanding (20-40 min):
Reading order: Methodology sections → Key figures → Evaluation/Results setup.
Goal: Understand what was built and how it was evaluated.
For each step, specify which sections to read (use actual section names from the list above), the objective, 2-3 questions to answer, and expected output.

PASS 3 – Deep Analysis (1-2 hrs):
Reading order: Equations/Algorithms → Ablation studies → Limitations section.
Goal: Critical analysis of whether the method is sound and generalizable.
For each step, specify which sections to read, the objective, 2-3 questions to answer, and expected output.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps.
2. Each step must specify:
    - For the section_to_read field, only write actual section titles or section numbers from the paper (e.g. '3. Methodology', 'Results'). Never write 'Figure N' or 'Table N' as section references — these are not retrievable sections.
    - Instead, use two separate boolean fields:
      needs_figures: true if this step requires understanding a figure or diagram from that section
      needs_tables: true if this step requires understanding a table or data from that section
      These flags will be used to fetch the summarized figure and table content automatically.
   - Objective of this step.
    - 2-3 questions the reader should be able to answer after this step — CRITICAL: questions
      must be specific to THIS paper, referencing actual methods, metrics, datasets, model
      names, or numbers from the abstract, introduction, or conclusion. Generic questions
      like "What did the authors propose?" are not acceptable.
   - Expected output or insight.
3. Use needs_figures / needs_tables to indicate figure/table dependency for each step.
4. Keep instructions clear and actionable.

Always reference ACTUAL section names from the list above in your guide."""


# ---------------------------------------------------------------------------
# Category-specific guide prompts (Theoretical, Survey)
# ---------------------------------------------------------------------------

def theoretical_guide_prompt(
    title: str,
    abstract: str,
    introduction: str,
    conclusion: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0,
) -> str:
    """
    Generate a Three-Pass reading guide for THEORETICAL papers.

    Covers papers that formally prove or derive something: mathematical proofs,
    theorem/lemma statements, complexity analysis, formal methods, and
    mathematical derivations.

    Args:
        title: Paper title
        abstract: Paper abstract
        introduction: Paper introduction text
        conclusion: Paper conclusion text
        sections: List of section dictionaries with original_name field
        num_figures: Number of figures in the paper
        num_tables: Number of tables in the paper

    Returns:
        Formatted prompt for generating a THEORETICAL paper reading guide
    """
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])

    return f"""You are an expert research assistant helping users read theoretical and mathematical papers efficiently.

Generate a step-by-step reading guide for this THEORETICAL paper using the Three-Pass Method.
This paper formally proves or derives something (proofs, theorems, lemmas, complexity analysis, convergence analysis, formal methods, mathematical derivations).

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Introduction: {introduction}
- Conclusion: {conclusion}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

THREE PASS METHOD FOR THEORETICAL PAPERS:

PASS 1 – Quick Scan (5-10 min):
Reading order: Abstract → Introduction → Conclusion → Theorem/Lemma statements only (skip all proofs).
Goal: Understand WHAT was proven and WHY it matters, without getting lost in the proofs.
For each step, specify which sections to read (use actual section names from the list above), the objective, 2-3 questions to answer, and expected output.

PASS 2 – Proof Strategy (20-40 min):
Reading order: Definitions and Assumptions section → Theorem statements with their implications → Applications or Examples section.
Goal: Understand the CONDITIONS under which the results hold — not yet the full proof details.
For each step, specify which sections to read, the objective, 2-3 questions to answer, and expected output.

PASS 3 – Deep Mathematical Analysis (1-2 hrs):
Reading order: Proof details → Complexity analysis → Connection to related theoretical work.
Goal: Verify the reasoning and understand where assumptions could be relaxed.
For each step, specify which sections to read, the objective, 2-3 questions to answer, and expected output.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps.
2. Each step must specify:
    - For the section_to_read field, only write actual section titles or section numbers from the paper (e.g. '3. Methodology', 'Results'). Never write 'Figure N' or 'Table N' as section references — these are not retrievable sections.
    - Instead, use two separate boolean fields:
      needs_figures: true if this step requires understanding a figure or diagram from that section
      needs_tables: true if this step requires understanding a table or data from that section
      These flags will be used to fetch the summarized figure and table content automatically.
   - Objective of this step.
    - 2-3 questions the reader should be able to answer after this step — CRITICAL: questions must be
      specific to THIS paper, referencing actual theorem, lemma, corollary names, assumptions,
      notation, bounds, complexity results, or claims from the abstract, introduction, or conclusion.
      Generic questions like "What is proved?" are not acceptable.
   - Expected output or insight.
3. Flag specific theorem, lemma, and corollary names when they appear in the section headings.
4. Use needs_figures / needs_tables to indicate figure/table dependency for each step.
5. Keep instructions clear and actionable.

Always reference ACTUAL section names from the list above in your guide."""


def survey_guide_prompt(
    title: str,
    abstract: str,
    introduction: str,
    conclusion: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0,
) -> str:
    """
    Generate a Three-Pass reading guide for SURVEY papers.

    Covers surveys, reviews, literature reviews, meta-analyses, and overview papers.

    Args:
        title: Paper title
        abstract: Paper abstract
        introduction: Paper introduction text
        conclusion: Paper conclusion text
        sections: List of section dictionaries with original_name field
        num_figures: Number of figures in the paper
        num_tables: Number of tables in the paper

    Returns:
        Formatted prompt for generating a SURVEY paper reading guide
    """
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])

    return f"""You are an expert research assistant helping users read survey and review papers efficiently.

Generate a step-by-step reading guide for this SURVEY paper using the Three-Pass Method.
This paper surveys, reviews, or organizes existing research (survey, review, literature review, meta-analysis, overview).

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Introduction: {introduction}
- Conclusion: {conclusion}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

THREE PASS METHOD FOR SURVEY PAPERS:

PASS 1 – Field Overview (5-10 min):
Reading order: Abstract → Introduction → Conclusion → Taxonomy or categorization section headings → Research gaps / future directions.
Goal: Understand the SHAPE of the field, not the detail.
For each step, specify which sections to read (use actual section names from the list above), the objective, 2-3 questions to answer, and expected output.

PASS 2 – Taxonomy Understanding (20-40 min):
Reading order: Taxonomy section in full → Key findings per category → Comparison tables if present.
Goal: Build a mental map of how the field is organized.
For each step, specify which sections to read, the objective, 2-3 questions to answer, and expected output.
If the paper has {num_tables} tables, reference comparison tables where relevant.

PASS 3 – Research Landscape Analysis (1-2 hrs):
Reading order: Individual paper summaries for topics relevant to the reader → Reference list as a curated reading list.
Goal: Use this paper as a NAVIGATION TOOL, not a linear read.
For each step, specify which sections to read, the objective, 2-3 questions to answer, and expected output.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps.
2. Each step must specify:
    - For the section_to_read field, only write actual section titles or section numbers from the paper (e.g. '3. Methodology', 'Results'). Never write 'Figure N' or 'Table N' as section references — these are not retrievable sections.
    - Instead, use two separate boolean fields:
      needs_figures: true if this step requires understanding a figure or diagram from that section
      needs_tables: true if this step requires understanding a table or data from that section
      These flags will be used to fetch the summarized figure and table content automatically.
   - Objective of this step.
    - 2-3 questions the reader should be able to answer after this step — CRITICAL: questions must be
      specific to THIS survey, referencing actual taxonomy/category names, method families, trends,
      benchmark names, date ranges, or claims from the abstract, introduction, or conclusion.
      Generic questions like "What are the categories?" are not acceptable.
   - Expected output or insight.
3. Use needs_figures / needs_tables to indicate figure/table dependency for each step.
4. Keep instructions clear and actionable.

Always reference ACTUAL section names from the list above in your guide."""










