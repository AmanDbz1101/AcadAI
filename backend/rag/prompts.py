"""
Research Paper Assistant - Prompts
===================================
All LLM prompts consolidated in one place.

Follows the Chat2Code pattern: simple functions returning formatted strings.
"""

from typing import Optional


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
- If the content doesn't contain enough information, say so
- Use academic language but keep it accessible
- For technical questions, explain key concepts briefly

Format your answer as:
Direct answer (2-3 sentences)


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
        if not isinstance(section, dict):
            continue

        name = str(section.get("title") or section.get("original_name") or section.get("name") or "Untitled").strip()
        page_start = section.get("page_start")
        snippet = str(section.get("content_snippet") or "").strip()

        line = name
        if page_start is not None and str(page_start).strip():
            line = f"{line} (p.{page_start})"
        if snippet:
            line = f"{line}: {snippet}"

        result.append(line)
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

CRITICAL INSTRUCTION FOR QUESTION QUALITY:
Every question you generate MUST be specific to THIS paper.
A good question cannot be answered without reading this specific paper.

BAD (generic): "What methodology does the paper use?"
GOOD (specific): "Why do the authors use cross-entropy loss instead of MSE for the classification task, and how does their regularization approach differ from standard dropout?"

Use the section content snippets provided to anchor questions to actual claims, methods, numbers, and findings in this paper.
If a section snippet mentions a specific technique, dataset, metric, or result - your questions should reference it directly.

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
For each step, specify which sections to read, the objective, 1-2 questions to answer, and expected output.
If the paper has {num_figures} figures or {num_tables} tables, reference the most informative ones.

PASS 2 – Method Understanding (20-40 min):
Reading order: Methodology sections → Key figures → Evaluation/Results setup.
Goal: Understand what was built and how it was evaluated.
For each step, specify which sections to read (use actual section names from the list above), the objective, 1-2 questions to answer, and expected output.

PASS 3 – Deep Analysis (1-2 hrs):
Reading order: Equations/Algorithms → Ablation studies → Limitations section.
Goal: Critical analysis of whether the method is sound and generalizable.
For each step, specify which sections to read, the objective, 1-2 questions to answer, and expected output.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps.
2. Coverage and non-repetition rules:
    - The section 'Abstract' must appear in section_to_read at least once across the three passes.
    - Every section from the provided Section Headings list must appear in section_to_read at least once across all three passes, EXCEPT reference-style sections (References, Bibliography, Works Cited).
    - Do not repeat the same section in multiple steps within the same pass.
    - Prefer assigning leaf-level sections when subsection headings are available; do not assign broad parent sections when specific child sections exist.
3. Each step must specify:
    - For the section_to_read field, only write actual section titles or section numbers from the paper (e.g. '3. Methodology', 'Results'). Never write 'Figure N' or 'Table N' as section references — these are not retrievable sections.
    - Instead, use two separate boolean fields:
      needs_figures: true if this step requires understanding a figure or diagram from that section
      needs_tables: true if this step requires understanding a table or data from that section
      These flags will be used to fetch the summarized figure and table content automatically.
   - Objective of this step.
        - 1-2 questions the reader should be able to answer after this step. Keep questions
            short, concrete, and easy to answer from the section. Avoid heavy jargon or keyword
            stuffing. Questions should still be specific to THIS paper when possible.
   - Expected output or insight.
         - Include relevant_figure_ids and relevant_table_ids when available (use [] when none).
             Use string IDs (e.g., ["1", "2"]) rather than numbers.
4. Use needs_figures / needs_tables to indicate figure/table dependency for each step.
5. Keep instructions clear and actionable.
6. Before returning output, run a final self-check:
    - Abstract is assigned somewhere in the guide
    - all non-reference listed sections are assigned somewhere in the guide
    - no pass has duplicate section assignments
    - steps remain sequential and actionable

SELF-CHECK BEFORE RESPONDING:
1. Does each question reference something specific from the paper (a method name, a result, a dataset, a theorem)?
2. Could any question be asked about a different paper in the same field? If yes, make it more specific.
3. Does each pass cover a meaningfully different aspect of the paper?
4. Are all major sections represented across the 3 passes?

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
    critical_instruction = """
CRITICAL INSTRUCTION FOR QUESTION QUALITY:
Every question you generate MUST reference specific theorems, definitions, or proof steps from THIS paper.

BAD (generic): "What assumptions does the paper make?"
GOOD (specific): "Theorem 2 assumes bounded gradient norms - under what conditions does this assumption hold, and what breaks if it is violated in practice?"

Use the section content snippets to identify specific formal claims and proof strategies to ask about.
"""
    self_check_block = """
SELF-CHECK BEFORE RESPONDING:
1. Does each question reference something specific from the paper (a method name, a result, a dataset, a theorem)?
2. Could any question be asked about a different paper in the same field? If yes, make it more specific.
3. Does each pass cover a meaningfully different aspect of the paper?
4. Are all major sections represented across the 3 passes?
"""

    return f"""You are an expert research assistant helping users read theoretical and mathematical papers efficiently.

Generate a step-by-step reading guide for this THEORETICAL paper using the Three-Pass Method.
This paper formally proves or derives something (proofs, theorems, lemmas, complexity analysis, convergence analysis, formal methods, mathematical derivations).

{critical_instruction}

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
For each step, specify which sections to read (use actual section names from the list above), the objective, 1-2 questions to answer, and expected output.

PASS 2 – Proof Strategy (20-40 min):
Reading order: Definitions and Assumptions section → Theorem statements with their implications → Applications or Examples section.
Goal: Understand the CONDITIONS under which the results hold — not yet the full proof details.
For each step, specify which sections to read, the objective, 1-2 questions to answer, and expected output.

PASS 3 – Deep Mathematical Analysis (1-2 hrs):
Reading order: Proof details → Complexity analysis → Connection to related theoretical work.
Goal: Verify the reasoning and understand where assumptions could be relaxed.
For each step, specify which sections to read, the objective, 1-2 questions to answer, and expected output.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps.
2. Coverage and non-repetition rules:
    - The section 'Abstract' must appear in section_to_read at least once across the three passes.
    - Every section from the provided Section Headings list must appear in section_to_read at least once across all three passes, EXCEPT reference-style sections (References, Bibliography, Works Cited).
    - Do not repeat the same section in multiple steps within the same pass.
    - Prefer assigning leaf-level sections when subsection headings are available; do not assign broad parent sections when specific child sections exist.
3. Each step must specify:
    - For the section_to_read field, only write actual section titles or section numbers from the paper (e.g. '3. Methodology', 'Results'). Never write 'Figure N' or 'Table N' as section references — these are not retrievable sections.
    - Instead, use two separate boolean fields:
      needs_figures: true if this step requires understanding a figure or diagram from that section
      needs_tables: true if this step requires understanding a table or data from that section
      These flags will be used to fetch the summarized figure and table content automatically.
   - Objective of this step.
        - 1-2 questions the reader should be able to answer after this step. Keep questions
            short, concrete, and easy to answer from the section. Avoid heavy jargon or keyword
            stuffing. Questions should still be specific to THIS paper when possible.
   - Expected output or insight.
         - Include relevant_figure_ids and relevant_table_ids when available (use [] when none).
             Use string IDs (e.g., ["1", "2"]) rather than numbers.
4. Flag specific theorem, lemma, and corollary names when they appear in the section headings.
5. Use needs_figures / needs_tables to indicate figure/table dependency for each step.
6. Keep instructions clear and actionable.
7. Before returning output, run a final self-check:
    - Abstract is assigned somewhere in the guide
    - all non-reference listed sections are assigned somewhere in the guide
    - no pass has duplicate section assignments
    - steps remain sequential and actionable

{self_check_block}

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
    critical_instruction = """
CRITICAL INSTRUCTION FOR QUESTION QUALITY:
Every question MUST reference specific methods, papers, or categories discussed in this survey.

BAD (generic): "How do the methods compare?"
GOOD (specific): "The survey groups attention mechanisms into global and local categories - what is the computational complexity tradeoff between them and which works does the survey cite as representative of each?"

Use the section content snippets to identify the specific taxonomy, categories, and representative works being surveyed.
"""
    self_check_block = """
SELF-CHECK BEFORE RESPONDING:
1. Does each question reference something specific from the paper (a method name, a result, a dataset, a theorem)?
2. Could any question be asked about a different paper in the same field? If yes, make it more specific.
3. Does each pass cover a meaningfully different aspect of the paper?
4. Are all major sections represented across the 3 passes?
"""

    return f"""You are an expert research assistant helping users read survey and review papers efficiently.

Generate a step-by-step reading guide for this SURVEY paper using the Three-Pass Method.
This paper surveys, reviews, or organizes existing research (survey, review, literature review, meta-analysis, overview).

{critical_instruction}

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
For each step, specify which sections to read (use actual section names from the list above), the objective, 1-2 questions to answer, and expected output.

PASS 2 – Taxonomy Understanding (20-40 min):
Reading order: Taxonomy section in full → Key findings per category → Comparison tables if present.
Goal: Build a mental map of how the field is organized.
For each step, specify which sections to read, the objective, 1-2 questions to answer, and expected output.
If the paper has {num_tables} tables, reference comparison tables where relevant.

PASS 3 – Research Landscape Analysis (1-2 hrs):
Reading order: Individual paper summaries for topics relevant to the reader → Trend/gap synthesis sections.
Goal: Use this paper as a NAVIGATION TOOL, not a linear read.
For each step, specify which sections to read, the objective, 1-2 questions to answer, and expected output.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps.
2. Coverage and non-repetition rules:
    - The section 'Abstract' must appear in section_to_read at least once across the three passes.
    - Every section from the provided Section Headings list must appear in section_to_read at least once across all three passes, EXCEPT reference-style sections (References, Bibliography, Works Cited).
    - Do not repeat the same section in multiple steps within the same pass.
    - Prefer assigning leaf-level sections when subsection headings are available; do not assign broad parent sections when specific child sections exist.
3. Each step must specify:
    - For the section_to_read field, only write actual section titles or section numbers from the paper (e.g. '3. Methodology', 'Results'). Never write 'Figure N' or 'Table N' as section references — these are not retrievable sections.
    - Instead, use two separate boolean fields:
      needs_figures: true if this step requires understanding a figure or diagram from that section
      needs_tables: true if this step requires understanding a table or data from that section
      These flags will be used to fetch the summarized figure and table content automatically.
   - Objective of this step.
        - 1-2 questions the reader should be able to answer after this step. Keep questions
            short, concrete, and easy to answer from the section. Avoid heavy jargon or keyword
            stuffing. Questions should still be specific to THIS paper when possible.
   - Expected output or insight.
         - Include relevant_figure_ids and relevant_table_ids when available (use [] when none).
             Use string IDs (e.g., ["1", "2"]) rather than numbers.
4. Use needs_figures / needs_tables to indicate figure/table dependency for each step.
5. Keep instructions clear and actionable.
6. Before returning output, run a final self-check:
    - Abstract is assigned somewhere in the guide
    - all non-reference listed sections are assigned somewhere in the guide
    - no pass has duplicate section assignments
    - steps remain sequential and actionable

{self_check_block}

Always reference ACTUAL section names from the list above in your guide."""


def _planner_visual_id_block(
    available_figure_ids: list[str] | None,
    available_table_ids: list[str] | None,
    section_visual_index_json: str,
) -> str:
    figure_ids = available_figure_ids or []
    table_ids = available_table_ids or []
    return (
        "VISUAL ID CONTEXT:\n"
        f"- Available figure IDs: {figure_ids}\n"
        f"- Available table IDs: {table_ids}\n"
        "- Section-to-visual mapping JSON (use this to assign relevant IDs per step):\n"
        f"{section_visual_index_json}\n"
    )


def applied_guide_planner_prompt(
    title: str,
    abstract: str,
    introduction: str,
    conclusion: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0,
    available_figure_ids: list[str] | None = None,
    available_table_ids: list[str] | None = None,
    section_visual_index_json: str = "{}",
) -> str:
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])
    visual_block = _planner_visual_id_block(
        available_figure_ids=available_figure_ids,
        available_table_ids=available_table_ids,
        section_visual_index_json=section_visual_index_json,
    )

    return f"""You are Agent 1: Reading Guide Planner for APPLIED papers.

Return only the guide skeleton. Do not generate questions yet.

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Introduction: {introduction}
- Conclusion: {conclusion}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

{visual_block}

RULES:
1. Build a three-pass guide skeleton with sequential steps.
2. section_to_read must use only actual section names from Section Headings.
3. Follow the three-pass method faithfully; do NOT force complete coverage of all sections.
4. Prefer leaf sections when available and only include sections necessary for each pass goal.
5. Avoid repeating the same section across steps and across passes by default.
6. Repeat a section only when truly necessary after prerequisite reading, and make that revisit intent explicit in the objective.
7. Exclude References/Bibliography/Works Cited unless a specific step explicitly requires them.
8. For every step, include:
     - relevant_figure_ids: figure IDs relevant to that step (empty list [] when none)
         Use string IDs (e.g., ["1", "2"]).
     - relevant_table_ids: table IDs relevant to that step (empty list [] when none)
         Use string IDs (e.g., ["1", "2"]).
   - needs_figures / needs_tables booleans aligned to the selected IDs
9. questions_to_answer must be an empty list [] for every step.

OUTPUT REQUIREMENTS:
- Return valid JSON matching the plan schema only.
- Do not include prose outside JSON.
"""


def theoretical_guide_planner_prompt(
    title: str,
    abstract: str,
    introduction: str,
    conclusion: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0,
    available_figure_ids: list[str] | None = None,
    available_table_ids: list[str] | None = None,
    section_visual_index_json: str = "{}",
) -> str:
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])
    visual_block = _planner_visual_id_block(
        available_figure_ids=available_figure_ids,
        available_table_ids=available_table_ids,
        section_visual_index_json=section_visual_index_json,
    )

    return f"""You are Agent 1: Reading Guide Planner for THEORETICAL papers.

Return only the guide skeleton. Do not generate questions yet.

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Introduction: {introduction}
- Conclusion: {conclusion}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

{visual_block}

RULES:
1. Build a three-pass guide skeleton with sequential steps.
2. section_to_read must use only actual section names from Section Headings.
3. Follow the three-pass method faithfully; do NOT force complete coverage of all sections.
4. Prefer leaf sections when available and only include sections necessary for each pass goal.
5. Avoid repeating the same section across steps and across passes by default.
6. Repeat a section only when truly necessary after prerequisite reading, and make that revisit intent explicit in the objective.
7. Exclude References/Bibliography/Works Cited unless a specific step explicitly requires them.
8. Include relevant_figure_ids / relevant_table_ids and aligned needs_figures / needs_tables.
9. questions_to_answer must be an empty list [] for every step.

OUTPUT REQUIREMENTS:
- Return valid JSON matching the plan schema only.
- Do not include prose outside JSON.
"""


def survey_guide_planner_prompt(
    title: str,
    abstract: str,
    introduction: str,
    conclusion: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0,
    available_figure_ids: list[str] | None = None,
    available_table_ids: list[str] | None = None,
    section_visual_index_json: str = "{}",
) -> str:
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])
    visual_block = _planner_visual_id_block(
        available_figure_ids=available_figure_ids,
        available_table_ids=available_table_ids,
        section_visual_index_json=section_visual_index_json,
    )

    return f"""You are Agent 1: Reading Guide Planner for SURVEY papers.

Return only the guide skeleton. Do not generate questions yet.

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Introduction: {introduction}
- Conclusion: {conclusion}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

{visual_block}

RULES:
1. Build a three-pass guide skeleton with sequential steps.
2. section_to_read must use only actual section names from Section Headings.
3. Follow the three-pass method faithfully; do NOT force complete coverage of all sections.
4. Prefer leaf sections when available and only include sections necessary for each pass goal.
5. Avoid repeating the same section across steps and across passes by default.
6. Repeat a section only when truly necessary after prerequisite reading, and make that revisit intent explicit in the objective.
7. Exclude References/Bibliography/Works Cited unless a specific step explicitly requires them.
8. Include relevant_figure_ids / relevant_table_ids and aligned needs_figures / needs_tables.
9. questions_to_answer must be an empty list [] for every step.

OUTPUT REQUIREMENTS:
- Return valid JSON matching the plan schema only.
- Do not include prose outside JSON.
"""


def guide_step_question_prompt(
    category: str,
    title: str,
    abstract: str,
    pass_key: str,
    pass_goal: str,
    step_number: int,
    section_to_read: list[str],
    objective: str,
    expected_output: str,
    figure_summaries: list[str] | None = None,
    table_summaries: list[str] | None = None,
) -> str:
    figures = figure_summaries or []
    tables = table_summaries or []
    return f"""You are Agent 2: Per-step Question Generator.

Generate exactly 3 paper-specific questions for one reading-guide step.

Paper category: {category}
Paper title: {title}
Paper abstract: {abstract}
Pass key: {pass_key}
Pass goal: {pass_goal}
Step number: {step_number}
Step sections: {section_to_read}
Step objective: {objective}
Step expected output: {expected_output}
Relevant figure summaries: {figures}
Relevant table summaries: {tables}

STRICT CONSTRAINTS:
1. Return exactly 3 questions as a JSON array of strings.
2. Each string must be a single standalone question.
3. Each question must contain exactly one question mark and end with '?'.
4. Do not write compound questions joined by 'and'.
5. Questions must be specific to this paper (method names, metrics, claims, datasets, theorem names, categories, or numerical results).
6. Avoid generic templates.

OUTPUT FORMAT (strict):
["question 1?", "question 2?", "question 3?"]
"""










