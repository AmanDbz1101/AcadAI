"""
Research Paper Assistant - Prompts
===================================
All LLM prompts consolidated in one place.

Follows the Chat2Code pattern: simple functions returning formatted strings.
"""


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


def retriever_prompt(query: str, category: str) -> str:
    """
    Generate a retrieval query optimization prompt.
    
    Expands and enriches user queries for better vector search results.
    
    Args:
        query: Original user query
        category: Paper category (helps tailor query expansion)
        
    Returns:
        Formatted prompt for query expansion
    """
    return f"""You are a semantic search query optimizer for academic papers.

Your task is to expand and enrich the user's query to improve retrieval from a vector database of research paper content.

Paper Category: {category}

User Query: {query}

Instructions:
- Identify key technical terms and concepts
- Add relevant synonyms and related terminology
- Consider section-specific language (e.g., "method", "results", "conclusion")
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
