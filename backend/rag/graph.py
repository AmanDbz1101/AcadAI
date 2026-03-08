"""
Research Paper Assistant - Graph
=================================
Unified LangGraph workflow for paper analysis.

Follows the Chat2Code pattern: simple, elegant node functions with lazy agent initialization.

Workflow paths:
    1. Extraction + Categorization:
       START → extraction → categorizer → END
    
    2. Q&A (with query):
       START → extraction → categorizer → retriever → qa → END
    
    3. Summarization (no query, not ORIGINAL_RESEARCH):
       START → extraction → categorizer → summarizer → END
    
    4. Reading Guide (ORIGINAL_RESEARCH, no query):
       START → extraction → categorizer → original_paper_guide → END
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from rag.states import AgentState, RetrievalResult
from rag.prompts import (
    categorizer_prompt,
    qa_prompt,
    summarizer_prompt,
    original_paper_guide_prompt,
    survey_review_guide_prompt,
    system_engineering_guide_prompt,
    theoretical_guide_prompt,
    benchmark_dataset_guide_prompt,
)
from rag.guide_models import (
    ReadingGuide,
    SurveyReadingGuide,
    SystemEngineeringReadingGuide,
    TheoreticalReadingGuide,
    BenchmarkDatasetReadingGuide,
)

# ---------------------------------------------------------------------------
# Guide helper: extract questions_to_answer and sections_to_read from any guide
# ---------------------------------------------------------------------------

def _extract_guide_retrieval_info(guide_json: dict) -> list[dict]:
    """
    Walk all ReadingPass objects inside a guide dict and return a flat list of
    per-question entries, each carrying **only the sections from that step**.

    Return format::

        [
            {"question": "...", "sections": ["Abstract", "1 Introduction"]},
            {"question": "...", "sections": ["3 Model Architecture"]},
            ...
        ]

    Multiple questions that belong to the same step share the same sections list
    (the exact sections listed for that step only — not accumulating across steps).

    Works for all five guide shapes (original_research, survey, system, theoretical, benchmark).
    """
    pairs: list[dict] = []
    seen_questions: set[str] = set()

    # All known pass keys across the five guide models
    pass_keys = [
        "pass1_quick_scan",
        "pass2_method_understanding",
        "pass3_deep_analysis",
        "pass1_field_overview",
        "pass2_taxonomy_understanding",
        "pass3_research_landscape_analysis",
        "pass1_system_overview",
        "pass2_architecture_deep_dive",
        "pass3_engineering_evaluation",
        "pass1_results_overview",
        "pass2_proof_strategy",
        "pass3_deep_mathematical_analysis",
        "pass1_dataset_overview",
        "pass2_methodology_and_tasks",
        "pass3_benchmark_analysis",
    ]

    for key in pass_keys:
        reading_pass = guide_json.get(key)
        if not reading_pass:
            continue
        for step in reading_pass.get("steps", []):
            # Sections are scoped to this step only
            step_sections = [s for s in step.get("section_to_read", []) if s]
            for q in step.get("questions_to_answer", []):
                if q and q not in seen_questions:
                    seen_questions.add(q)
                    pairs.append({"question": q, "sections": step_sections})

    return pairs


# Retrieval pipeline (lazy singleton — imported here to keep graph.py clean)
_retrieval_pipeline = None


def _get_retrieval_pipeline():
    """Return a process-wide RetrievalPipeline singleton."""
    global _retrieval_pipeline
    if _retrieval_pipeline is None:
        from rag.retrieval import RetrievalPipeline

        _retrieval_pipeline = RetrievalPipeline()
    return _retrieval_pipeline

# Import extraction orchestrator
import sys
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from backend.extraction.extraction import PDFExtractor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON extraction helper (from old categorizer_agent.py)
# ---------------------------------------------------------------------------
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from LLM response."""
    # Try markdown-fenced JSON first
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return json.loads(match.group(1))
    
    # Try parsing the whole response as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Last resort – find the first {...} span
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return json.loads(text[start:end])
    
    raise ValueError(f"No valid JSON found in LLM response:\n{text}")


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def extraction_node(state: dict) -> dict:
    """
    Extract metadata and content from PDF.
    
    Entry point for the workflow when starting from a PDF file.
    """
    logger.info("🔍 Extraction node: processing PDF...")
    
    pdf_path = state.get("pdf_path")
    if not pdf_path:
        return {
            **state,
            "errors": [*state.get("errors", []), "No pdf_path provided for extraction"],
        }
    
    force_ocr = state.get("force_ocr", False)
    
    try:
        # Get Groq API key from environment (needed for extraction metadata LLM)
        from config import GROQ_API_KEY
        extractor = PDFExtractor(groq_api_key=GROQ_API_KEY)
        
        # Run extraction
        result = extractor.extract(
            pdf_path=pdf_path,
            output_dir=Path("output"),
            force_ocr=force_ocr
        )
        
        # Map extraction results to state
        metadata = result["metadata"]
        return {
            **state,
            "document_id": result["document_id"],
            "full_text": result["full_text"],
            "title": metadata.get("paper_title", ""),
            "abstract": metadata.get("abstract", ""),
            "sections": metadata.get("sections", []),
            "hierarchy": result["hierarchy"],
            "extraction_files": result.get("files", {}),
        }
        
    except Exception as exc:
        logger.error(f"Extraction failed: {exc}")
        return {
            **state,
            "errors": [*state.get("errors", []), f"Extraction error: {exc}"],
        }


def categorizer_node(state: dict) -> dict:
    """
    Classify the paper into one of five categories.
    
    Uses title and abstract extracted in previous step.
    """
    logger.info("📚 Categorizer node: classifying paper...")
    
    title = state.get("title", "").strip()
    abstract = state.get("abstract", "").strip()
    
    if not title or not abstract:
        return {
            **state,
            "errors": [*state.get("errors", []), "Missing title or abstract for categorization"],
            "confidence": "LOW",
        }
    
    try:
        llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
        prompt = categorizer_prompt(title=title, abstract=abstract)
        response = llm.invoke([HumanMessage(content=prompt)])
        
        # Extract JSON from response
        parsed = _extract_json(response.content)
        
        category = parsed.get("category", "").strip().upper()
        confidence = parsed.get("confidence", "").strip().upper()
        reasoning = parsed.get("reasoning", "").strip()
        
        # Validate category
        valid_categories = {
            "ORIGINAL_RESEARCH",
            "SURVEY_REVIEW",
            "SYSTEM_ENGINEERING",
            "THEORETICAL",
            "BENCHMARK_DATASET",
        }
        if category not in valid_categories:
            logger.warning(f"Invalid category: {category}")
            category = None
        
        # Validate confidence
        valid_confidence = {"HIGH", "MEDIUM", "LOW"}
        if confidence not in valid_confidence:
            confidence = "LOW"
        
        return {
            **state,
            "category": category,
            "confidence": confidence,
            "category_reasoning": reasoning,
        }
        
    except Exception as exc:
        logger.error(f"Categorization failed: {exc}")
        return {
            **state,
            "errors": [*state.get("errors", []), f"Categorization error: {exc}"],
            "confidence": "LOW",
        }


def retriever_node(state: dict) -> dict:
    """
    Retrieve relevant content using hybrid vector search (dense + sparse BM25).

    Steps
    -----
    1. Use ``question_section_pairs`` from the guide (preferred) or fall back to
       a single user query.  Each pair carries the question **and the sections
       that belong only to that step** — no cross-step accumulation.
    2. Lazy-index the document into Qdrant once before the loop.
    3. Per-question hybrid retrieval (BGE dense + BM25 sparse, RRF fusion)
       with section boosting scoped to that step's sections.
    4. Results are stored **per question** in ``per_question_results`` — no merging.
    """
    logger.info("🔎 Retriever node: hybrid search …")

    question_section_pairs = state.get("question_section_pairs") or []
    user_query = (state.get("query") or "").strip()
    category = state.get("category", "ORIGINAL_RESEARCH")
    document_id = state.get("document_id", "")

    # Build the list of (question, sections) pairs to process
    if question_section_pairs:
        pairs = question_section_pairs  # each: {"question": str, "sections": list[str]}
        logger.info("Using %d per-step guide (question, sections) pairs", len(pairs))
    elif user_query:
        pairs = [{"question": user_query, "sections": []}]
        logger.info("Using user query for retrieval: %s…", user_query[:80])
    else:
        return {
            **state,
            "errors": [*state.get("errors", []), "No query provided for retrieval"],
        }

    try:
        # ── Lazy indexing (once before the query loop) ────────────────────────
        pipeline = _get_retrieval_pipeline()

        if document_id:
            hierarchy_path = Path("output") / f"{document_id}_hierarchy.json"
            if hierarchy_path.exists():
                index_result = pipeline.index(
                    hierarchy_json_path=hierarchy_path,
                    output_dir=Path("output"),
                )
                if not index_result.skipped:
                    logger.info(
                        "Indexed %d chunks for document %s",
                        index_result.total_chunks,
                        document_id,
                    )
            else:
                logger.warning(
                    "Hierarchy file not found for document %s; skipping indexing",
                    document_id,
                )

        # ── Per-question expand + retrieve (results kept separate) ────────────
        per_question_results: list[dict] = []

        for i, pair in enumerate(pairs, 1):
            raw_q = pair["question"]
            # Only this step's sections — not any other step's
            step_sections: list[str] = pair.get("sections") or []

            logger.info(
                "  [%d/%d] Q: %s…  step_sections=%s",
                i, len(pairs), raw_q[:70], step_sections,
            )

            # Section-boosted passes using *this step's* sections only,
            # then one unrestricted pass for broader coverage
            step_hits: list = []
            seen_content: set = set()

            if step_sections:
                for section in step_sections:
                    sec_hits = pipeline.query(
                        query=raw_q,
                        document_id=document_id or None,
                        section_title_contains=section,
                    )
                    for r in sec_hits:
                        key = r.content[:120] if hasattr(r, "content") else str(r)
                        if key not in seen_content:
                            seen_content.add(key)
                            step_hits.append(r)

            # Unrestricted pass
            for r in pipeline.query(query=raw_q, document_id=document_id or None):
                key = r.content[:120] if hasattr(r, "content") else str(r)
                if key not in seen_content:
                    seen_content.add(key)
                    step_hits.append(r)

            logger.info("      → %d chunks retrieved", len(step_hits))

            per_question_results.append({
                "question": raw_q,
                "sections": step_sections,
                "chunks": [r.model_dump() for r in step_hits],
            })

        logger.info(
            "Retrieval complete: %d questions, results stored separately",
            len(per_question_results),
        )

        return {
            **state,
            "per_question_results": per_question_results,
        }

    except Exception as exc:
        logger.error("Retrieval failed: %s", exc, exc_info=True)
        return {
            **state,
            "errors": [*state.get("errors", []), f"Retrieval error: {exc}"],
        }


def qa_node(state: dict) -> dict:
    """
    Answer user's question using retrieved context.
    
    Follows retriever_node in the Q&A workflow path.
    """
    logger.info("💬 Q&A node: generating answer...")
    
    query = state.get("query", "")
    retrieval_results = state.get("retrieval_results", [])
    
    if not query:
        return {
            **state,
            "errors": [*state.get("errors", []), "No query provided for Q&A"],
        }
    
    if not retrieval_results:
        return {
            **state,
            "errors": [*state.get("errors", []), "No retrieval results for Q&A"],
            "answer": "I couldn't find relevant information to answer your question.",
            "answer_confidence": "LOW",
        }
    
    try:
        # Build context from retrieval results
        context_parts = []
        for i, result in enumerate(retrieval_results[:5], 1):
            content = result.get("content", "")
            score = result.get("score", 0.0)
            context_parts.append(f"[{i}] (relevance: {score:.2f})\n{content}")
        
        context = "\n\n".join(context_parts)
        
        # Prepare metadata
        metadata = {
            "paper_title": state.get("title", ""),
            "category": state.get("category", ""),
        }
        
        # Generate answer
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)
        prompt = qa_prompt(query=query, context=context, metadata=metadata)
        response = llm.invoke([HumanMessage(content=prompt)])
        
        answer = response.content.strip()
        
        # Simple confidence heuristic based on answer length and completeness
        answer_confidence = "HIGH" if len(answer) > 100 else "MEDIUM"
        
        return {
            **state,
            "answer": answer,
            "answer_confidence": answer_confidence,
        }
        
    except Exception as exc:
        logger.error(f"Q&A failed: {exc}")
        return {
            **state,
            "errors": [*state.get("errors", []), f"Q&A error: {exc}"],
            "answer": "An error occurred while generating the answer.",
            "answer_confidence": "LOW",
        }


def summarizer_node(state: dict) -> dict:
    """
    Generate a structured summary of the paper.
    
    Alternative to Q&A when no query is provided.
    """
    logger.info("📝 Summarizer node: generating summary...")
    
    title = state.get("title", "")
    abstract = state.get("abstract", "")
    sections = state.get("sections", [])
    category = state.get("category", "ORIGINAL_RESEARCH")
    
    if not title or not abstract:
        return {
            **state,
            "errors": [*state.get("errors", []), "Missing title or abstract for summarization"],
        }
    
    try:
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)
        prompt = summarizer_prompt(
            title=title,
            abstract=abstract,
            sections=sections,
            category=category
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        
        summary = response.content.strip()
        
        # Simple extraction of key contributions (look for numbered list)
        contributions = []
        lines = summary.split("\n")
        for line in lines:
            if re.match(r"^\d+\.", line.strip()):
                contributions.append(line.strip())
        
        return {
            **state,
            "summary": summary,
            "key_contributions": contributions if contributions else None,
        }
        
    except Exception as exc:
        logger.error(f"Summarization failed: {exc}")
        return {
            **state,
            "errors": [*state.get("errors", []), f"Summarization error: {exc}"],
        }


def _run_guide_node(
    state: dict,
    label: str,
    guide_model_cls,
    prompt_fn,
) -> dict:
    """
    Generic helper called by all five guide nodes.

    Parameters
    ----------
    state         : current workflow state
    label         : human-readable label for logging (e.g. "ORIGINAL_RESEARCH")
    guide_model_cls : Pydantic model class for structured output
    prompt_fn     : function(title, abstract, sections, num_figures, num_tables) → str
    """
    logger.info("📖 Guide node [%s]: generating reading guide…", label)

    title = state.get("title", "")
    abstract = state.get("abstract", "")
    sections = state.get("sections", [])
    document_id = state.get("document_id", "")

    if not title or not abstract:
        return {
            **state,
            "errors": [*state.get("errors", []), f"Missing title or abstract for {label} guide"],
        }

    try:
        num_figures = sum(s.get("stats", {}).get("figures", 0) for s in sections)
        num_tables = sum(s.get("stats", {}).get("tables", 0) for s in sections)

        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1)
        structured_llm = llm.with_structured_output(guide_model_cls)

        prompt = prompt_fn(
            title=title,
            abstract=abstract,
            sections=sections,
            num_figures=num_figures,
            num_tables=num_tables,
        )

        guide_model = structured_llm.invoke(prompt)
        guide_json = guide_model.model_dump()

        # Extract per-question (question, step_sections) pairs from the guide
        question_section_pairs = _extract_guide_retrieval_info(guide_json)
        # Flat lists kept for display / backward compat
        questions = [p["question"] for p in question_section_pairs]
        all_sections = list(dict.fromkeys(s for p in question_section_pairs for s in p["sections"]))
        logger.info(
            "Guide [%s]: extracted %d questions across %d unique sections for retrieval",
            label, len(questions), len(all_sections),
        )

        # Persist guide to disk
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        guide_path = output_dir / f"{document_id}_guide.json"
        with open(guide_path, "w", encoding="utf-8") as f:
            json.dump(guide_json, f, indent=2, ensure_ascii=False)
        logger.info("✅ Reading guide saved to: %s", guide_path)

        return {
            **state,
            "reading_guide": guide_json,
            "guide_file_path": str(guide_path),
            "question_section_pairs": question_section_pairs,
            # Flat versions kept for display
            "questions_to_answer": questions,
            "sections_to_read": all_sections,
        }

    except Exception as exc:
        logger.error("Guide generation [%s] failed: %s", label, exc)
        return {
            **state,
            "errors": [*state.get("errors", []), f"Guide generation error [{label}]: {exc}"],
        }


def original_paper_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for ORIGINAL_RESEARCH papers."""
    return _run_guide_node(
        state,
        label="ORIGINAL_RESEARCH",
        guide_model_cls=ReadingGuide,
        prompt_fn=original_paper_guide_prompt,
    )


def survey_review_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for SURVEY_REVIEW papers."""
    return _run_guide_node(
        state,
        label="SURVEY_REVIEW",
        guide_model_cls=SurveyReadingGuide,
        prompt_fn=survey_review_guide_prompt,
    )


def system_engineering_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for SYSTEM_ENGINEERING papers."""
    return _run_guide_node(
        state,
        label="SYSTEM_ENGINEERING",
        guide_model_cls=SystemEngineeringReadingGuide,
        prompt_fn=system_engineering_guide_prompt,
    )


def theoretical_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for THEORETICAL papers."""
    return _run_guide_node(
        state,
        label="THEORETICAL",
        guide_model_cls=TheoreticalReadingGuide,
        prompt_fn=theoretical_guide_prompt,
    )


def benchmark_dataset_guide_node(state: dict) -> dict:
    """Generate a Three-Pass reading guide for BENCHMARK_DATASET papers."""
    return _run_guide_node(
        state,
        label="BENCHMARK_DATASET",
        guide_model_cls=BenchmarkDatasetReadingGuide,
        prompt_fn=benchmark_dataset_guide_prompt,
    )



# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------

# Category → guide node name mapping (used in routing and graph wiring)
_CATEGORY_GUIDE_NODE = {
    "ORIGINAL_RESEARCH": "original_paper_guide",
    "SURVEY_REVIEW": "survey_review_guide",
    "SYSTEM_ENGINEERING": "system_engineering_guide",
    "THEORETICAL": "theoretical_guide",
    "BENCHMARK_DATASET": "benchmark_dataset_guide",
}


def route_after_categorizer(state: dict) -> str:
    """
    Route after categorization.

    Routing logic (no query path — generate reading guide based on category):
    - ORIGINAL_RESEARCH  → original_paper_guide
    - SURVEY_REVIEW      → survey_review_guide
    - SYSTEM_ENGINEERING → system_engineering_guide
    - THEORETICAL        → theoretical_guide
    - BENCHMARK_DATASET  → benchmark_dataset_guide

    If a user query is provided directly (bypassing the guide flow) → summarizer.
    """
    query = (state.get("query") or "").strip()
    category = state.get("category", "")

    # If user provided a direct query without wanting a guide, go to summarizer
    # (The guide nodes will route to retriever themselves via their own edge)
    if query:
        logger.info("→ Routing to summarizer (direct query path — no guide generation)")
        return "summarizer"

    # Route to the appropriate category-specific guide node
    guide_node = _CATEGORY_GUIDE_NODE.get(category)
    if guide_node:
        logger.info("→ Routing to %s (category=%s)", guide_node, category)
        return guide_node

    # Fallback: summarize if category unknown
    logger.info("→ Routing to summarizer (fallback: unknown category %s)", category)
    return "summarizer"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph():
    """
    Build and compile the LangGraph pipeline.

    Workflow paths
    --------------
    Extraction + Categorization only (no query):
        START → extraction → categorizer → <category_guide> → retriever → END

    Guide nodes (one per category):
        original_paper_guide  (ORIGINAL_RESEARCH)
        survey_review_guide   (SURVEY_REVIEW)
        system_engineering_guide (SYSTEM_ENGINEERING)
        theoretical_guide     (THEORETICAL)
        benchmark_dataset_guide (BENCHMARK_DATASET)

    Each guide node extracts questions_to_answer + sections_to_read, then
    flows into the retriever.  The retriever returns the chunks as output
    (no LLM QA step for now).

    Direct query path (query provided by user):
        START → extraction → categorizer → summarizer → END

    Returns:
        A compiled LangGraph CompiledGraph ready for invocation.
    """
    builder = StateGraph(dict)

    # ── Nodes ──────────────────────────────────────────────────────────────
    builder.add_node("extraction", extraction_node)
    builder.add_node("categorizer", categorizer_node)

    # Five category-specific guide nodes
    builder.add_node("original_paper_guide", original_paper_guide_node)
    builder.add_node("survey_review_guide", survey_review_guide_node)
    builder.add_node("system_engineering_guide", system_engineering_guide_node)
    builder.add_node("theoretical_guide", theoretical_guide_node)
    builder.add_node("benchmark_dataset_guide", benchmark_dataset_guide_node)

    # Shared downstream nodes
    builder.add_node("retriever", retriever_node)
    builder.add_node("summarizer", summarizer_node)
    builder.add_node("qa", qa_node)  # kept for future use

    # ── Edges ──────────────────────────────────────────────────────────────
    builder.add_edge(START, "extraction")
    builder.add_edge("extraction", "categorizer")

    # Conditional routing: categorizer → one of the 5 guide nodes (or summarizer)
    builder.add_conditional_edges(
        "categorizer",
        route_after_categorizer,
        {
            "original_paper_guide": "original_paper_guide",
            "survey_review_guide": "survey_review_guide",
            "system_engineering_guide": "system_engineering_guide",
            "theoretical_guide": "theoretical_guide",
            "benchmark_dataset_guide": "benchmark_dataset_guide",
            "summarizer": "summarizer",
        },
    )

    # All five guide nodes flow into the shared retriever
    for guide_node in _CATEGORY_GUIDE_NODE.values():
        builder.add_edge(guide_node, "retriever")

    # Retriever → END  (chunks returned as output; no LLM QA step for now)
    builder.add_edge("retriever", END)

    # Summarizer and QA paths
    builder.add_edge("summarizer", END)
    builder.add_edge("qa", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------

_agent = None


def get_agent():
    """
    Return a lazily-initialized compiled agent with LangSmith tracing enabled.
    
    This constructs the graph and configures LangSmith on first call.
    The agent is cached for subsequent calls.
    """
    global _agent
    if _agent is not None:
        return _agent
    
    # Load environment variables
    load_dotenv()
    
    # Configure LangSmith tracing
    langsmith_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    if langsmith_enabled:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = os.getenv(
            "LANGCHAIN_ENDPOINT",
            "https://api.smith.langchain.com"
        )
        os.environ["LANGCHAIN_PROJECT"] = os.getenv(
            "LANGCHAIN_PROJECT",
            "ResearchPaperAssistant"
        )
        api_key = os.getenv("LANGCHAIN_API_KEY")
        if api_key:
            os.environ["LANGCHAIN_API_KEY"] = api_key
            logger.info("✅ LangSmith tracing enabled")
        else:
            logger.warning("⚠️  LANGCHAIN_TRACING_V2=true but LANGCHAIN_API_KEY not set")
    else:
        logger.info("LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true to enable)")
    
    # Build and cache the graph
    logger.info("Building research paper assistant graph...")
    _agent = build_graph()
    logger.info("✅ Graph compiled and ready")
    
    return _agent
