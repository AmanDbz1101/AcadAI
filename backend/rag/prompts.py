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
    
    Classifies research papers into 5 categories based on title and abstract.
    
    Args:
        title: Paper title
        abstract: Paper abstract
        
    Returns:
        Formatted prompt ready for LLM invocation
    """
    return f"""You are a research paper classification assistant.

Your task is to classify a research paper into ONE of the following five categories based ONLY on the provided title and abstract.

Categories:

1. ORIGINAL_RESEARCH
Papers that propose a new method, algorithm, model, architecture, or technique and usually include experiments comparing against baselines.

Typical signals:
- "we propose"
- "we introduce"
- "novel method"
- "new architecture"
- experimental results or benchmarks

2. SURVEY_REVIEW
Papers that summarize, review, or organize existing research in a field. They do not propose a new method but analyze prior work.

Typical signals:
- "survey"
- "review"
- "taxonomy"
- "overview of existing methods"
- discussion of many prior works

3. SYSTEM_ENGINEERING
Papers that describe the design and implementation of a real-world system, infrastructure, or engineering architecture.

Typical signals:
- system design
- architecture
- implementation
- deployment
- scalability
- engineering trade-offs

4. THEORETICAL
Papers focused on mathematical analysis, formal proofs, theoretical frameworks, or algorithmic complexity.

Typical signals:
- theorem
- lemma
- proof
- convergence analysis
- theoretical guarantees

5. BENCHMARK_DATASET
Papers that introduce a dataset, evaluation framework, or benchmark used to compare models or methods.

Typical signals:
- new dataset
- benchmark
- evaluation framework
- leaderboard
- dataset construction

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
    category = metadata.get("category", "ORIGINAL_RESEARCH")
    
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
        "ORIGINAL_RESEARCH": """
Focus on:
- Problem statement and motivation
- Proposed method/algorithm
- Key experimental results
- Main contributions
- Limitations and future work
""",
        "SURVEY_REVIEW": """
Focus on:
- Scope of the survey
- Taxonomy or categorization scheme
- Key findings across reviewed papers
- Research gaps identified
- Future research directions
""",
        "SYSTEM_ENGINEERING": """
Focus on:
- System architecture and design
- Engineering challenges and solutions
- Performance characteristics
- Deployment considerations
- Trade-offs and lessons learned
""",
        "THEORETICAL": """
Focus on:
- Main theoretical results (theorems/lemmas)
- Proof techniques used
- Complexity analysis
- Assumptions and conditions
- Implications and applications
""",
        "BENCHMARK_DATASET": """
Focus on:
- Dataset characteristics (size, scope, format)
- Collection and annotation process
- Benchmark tasks and metrics
- Baseline results
- Intended use cases
"""
    }
    
    guidance = category_guidance.get(category, category_guidance["ORIGINAL_RESEARCH"])
    
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


def original_paper_guide_prompt(
    title: str,
    abstract: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0
) -> str:
    """
    Generate a Three-Pass Method reading guide specifically for ORIGINAL RESEARCH papers.
    
    This prompt creates a detailed, step-by-step guide that helps students and researchers
    efficiently read and understand original research papers.
    
    Args:
        title: Paper title
        abstract: Paper abstract
        sections: List of section dictionaries with original_name field
        num_figures: Number of figures in the paper
        num_tables: Number of tables in the paper
        
    Returns:
        Formatted prompt for generating original paper reading guide
    """
    # Flatten nested sections and extract names
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])
    
    return f"""You are an expert research assistant helping users read research papers efficiently.

Generate a step-by-step reading guide for this ORIGINAL RESEARCH paper using the Three-Pass Method.

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

THREE PASS METHOD:

PASS 1 – Quick Scan (5-10 min): Understand main problem and contribution. Read title, abstract, intro, skim headings/figures, read conclusion.

PASS 2 – Method Understanding (20-40 min): Understand core method and experiments. Read method sections carefully, study key figures, understand evaluation setup and results.

PASS 3 – Deep Analysis (1-2 hrs): Critical technical analysis. Deep dive into equations/algorithms, analyze ablations, identify limitations and future work.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps
2. Each step specifies: sections to read, objective, questions to answer, expected output
3. Reference actual sections from the list above (use exact names or closest match)
4. Mention figures/tables when relevant
5. Keep instructions clear and actionable

Generate a comprehensive reading guide that helps students efficiently understand this paper.

IMPORTANT EXAMPLE:
Pass 1 step: Read "1 Introduction" to understand motivation and background
Pass 2 step: Study "3 Model Architecture" and "Figure 1" to understand the proposed method
Pass 3 step: Analyze "4.1 Ablation Study" to evaluate which components matter most

Always reference ACTUAL section names from the list above in your guide."""


# ---------------------------------------------------------------------------
# Category-specific guide prompts (Survey/Review, System Engineering, Theoretical, Benchmark)
# ---------------------------------------------------------------------------

def survey_review_guide_prompt(
    title: str,
    abstract: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0,
) -> str:
    """
    Generate a Three-Pass reading guide for SURVEY / REVIEW papers.
    Produces output matching the SurveyReadingGuide Pydantic model.
    """
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])

    return f"""You are an expert research assistant helping users read academic survey and review papers efficiently.

Generate a step-by-step reading guide for this SURVEY/REVIEW paper using the Three-Pass Method.

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

THREE PASS METHOD FOR SURVEYS:

PASS 1 – Field Overview (10-15 min): Grasp the survey's scope, the problem domain, and the taxonomy or categorization scheme introduced.

PASS 2 – Taxonomy & Method Categories (30-60 min): Study each major method category, understand how prior work is organized, note key comparisons and tables.

PASS 3 – Research Landscape Analysis (1-2 hrs): Identify research gaps, future directions, critical analysis of coverage, and evaluate the survey's completeness.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps
2. Each step specifies: sections to read, objective, questions to answer, expected output
3. Reference actual sections from the list above (use exact names or closest match)
4. Highlight any taxonomy figures or comparison tables when relevant
5. Keep instructions clear and actionable

Generate a comprehensive reading guide for students and researchers approaching this survey paper.

Always reference ACTUAL section names from the list above."""


def system_engineering_guide_prompt(
    title: str,
    abstract: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0,
) -> str:
    """
    Generate a Three-Pass reading guide for SYSTEM ENGINEERING papers.
    Produces output matching the SystemEngineeringReadingGuide Pydantic model.
    """
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])

    return f"""You are an expert research assistant helping users read system engineering and infrastructure papers efficiently.

Generate a step-by-step reading guide for this SYSTEM ENGINEERING paper using the Three-Pass Method.

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

THREE PASS METHOD FOR SYSTEM PAPERS:

PASS 1 – System Overview (5-10 min): Understand the system's purpose, the problem it solves, and the high-level architecture. Read abstract, intro, and skim architecture diagrams.

PASS 2 – Architecture Deep Dive (30-50 min): Study individual components, data flow, key design decisions, APIs, and implementation trade-offs in detail.

PASS 3 – Engineering Evaluation (1-1.5 hrs): Critically evaluate performance benchmarks, scalability results, failure modes, deployment lessons, and compare design choices to alternatives.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps
2. Each step specifies: sections to read, objective, questions to answer, expected output
3. Reference actual sections from the list above (use exact names or closest match)
4. Highlight architecture diagrams and performance tables when relevant
5. Keep instructions clear and actionable

Generate a comprehensive reading guide for engineers and researchers studying this system paper.

Always reference ACTUAL section names from the list above."""


def theoretical_guide_prompt(
    title: str,
    abstract: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0,
) -> str:
    """
    Generate a Three-Pass reading guide for THEORETICAL papers.
    Produces output matching the TheoreticalReadingGuide Pydantic model.
    """
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])

    return f"""You are an expert research assistant helping users read theoretical and mathematical computer science papers efficiently.

Generate a step-by-step reading guide for this THEORETICAL paper using the Three-Pass Method.

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

THREE PASS METHOD FOR THEORETICAL PAPERS:

PASS 1 – Results Overview (10-15 min): Understand what theorems or results are proved, why they matter, and what problem they solve — without diving into proofs yet.

PASS 2 – Proof Strategy (30-60 min): Follow the main mathematical argument: identify key lemmas, understand the proof structure, and trace how lemmas combine into the main result.

PASS 3 – Deep Mathematical Analysis (1-3 hrs): Rigorously verify individual proofs, assess assumptions and conditions, identify subtle steps, and connect the results to broader algorithmic or theoretical implications.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps
2. Each step specifies: sections to read, objective, questions to answer, expected output
3. Reference actual sections from the list above (use exact names or closest match)
4. Flag specific theorem / lemma / corollary names when mentioned in the section headings
5. Keep instructions clear and actionable

Generate a comprehensive reading guide for students and researchers working through this theoretical paper.

Always reference ACTUAL section names from the list above."""


def benchmark_dataset_guide_prompt(
    title: str,
    abstract: str,
    sections: list,
    num_figures: int = 0,
    num_tables: int = 0,
) -> str:
    """
    Generate a Three-Pass reading guide for BENCHMARK / DATASET papers.
    Produces output matching the BenchmarkDatasetReadingGuide Pydantic model.
    """
    section_names = _flatten_sections(sections)
    section_list = "\n".join([f"- {name}" for name in section_names])

    return f"""You are an expert research assistant helping users read benchmark and dataset papers efficiently.

Generate a step-by-step reading guide for this BENCHMARK/DATASET paper using the Three-Pass Method.

PAPER INFORMATION:
- Title: {title}
- Abstract: {abstract}
- Section Headings:
{section_list}
- Number of Figures: {num_figures}
- Number of Tables: {num_tables}

THREE PASS METHOD FOR BENCHMARK/DATASET PAPERS:

PASS 1 – Dataset Overview (5-10 min): Understand what dataset or benchmark is introduced, its intended use cases, scale, and the gap it fills compared to existing resources.

PASS 2 – Methodology & Tasks (30-50 min): Study data collection and annotation methodology, benchmark tasks, evaluation metrics, and the instructions/interfaces provided to annotators or models.

PASS 3 – Benchmark Analysis (1-1.5 hrs): Critically evaluate baseline model results, inter-annotator agreement or data quality metrics, dataset limitations, potential biases, and future research directions.

INSTRUCTIONS:
1. For each pass, create 3-5 sequential steps
2. Each step specifies: sections to read, objective, questions to answer, expected output
3. Reference actual sections from the list above (use exact names or closest match)
4. Highlight statistics tables, leaderboard tables, and annotation pipeline figures when relevant
5. Keep instructions clear and actionable

Generate a comprehensive reading guide for researchers wanting to understand, use, or build on this dataset/benchmark.

Always reference ACTUAL section names from the list above."""

