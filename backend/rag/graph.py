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
    
    3. Summarization (no query):
       START → extraction → categorizer → summarizer → END
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
    retriever_prompt,
    qa_prompt,
    summarizer_prompt,
)

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
    Retrieve relevant content from vector store.
    
    Only runs when user provides a query.
    """
    logger.info("🔎 Retriever node: searching vector store...")
    
    query = state.get("query", "").strip()
    category = state.get("category", "ORIGINAL_RESEARCH")
    
    if not query:
        return {
            **state,
            "errors": [*state.get("errors", []), "No query provided for retrieval"],
        }
    
    try:
        # First, optimize the query using LLM
        llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
        prompt = retriever_prompt(query=query, category=category)
        response = llm.invoke([HumanMessage(content=prompt)])
        optimized_query = response.content.strip()
        
        logger.info(f"Optimized query: {optimized_query}")
        
        # TODO: Implement actual Qdrant search
        # For now, return placeholder (will be implemented when Qdrant is integrated)
        # from qdrant_client import QdrantClient
        # client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        # results = client.search(...)
        
        # Placeholder: use sections from extraction as pseudo-retrieval
        sections = state.get("sections", [])
        retrieval_results = []
        for i, section in enumerate(sections[:3]):  # Top 3 sections as placeholder
            retrieval_results.append(
                RetrievalResult(
                    content=section.get("title", ""),
                    score=1.0 - (i * 0.1),
                    metadata={"section_index": i, "source": "extraction"}
                ).model_dump()
            )
        
        return {
            **state,
            "retrieval_query": optimized_query,
            "retrieval_results": retrieval_results,
        }
        
    except Exception as exc:
        logger.error(f"Retrieval failed: {exc}")
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


# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------

def route_after_categorizer(state: dict) -> str:
    """
    Route after categorization based on whether query exists.
    
    - If query exists → retriever (Q&A path)
    - If no query → summarizer (summary path)
    """
    query = state.get("query", "").strip()
    
    if query:
        logger.info("→ Routing to retriever (Q&A path)")
        return "retriever"
    else:
        logger.info("→ Routing to summarizer (summary path)")
        return "summarizer"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph():
    """
    Build and compile the LangGraph pipeline.
    
    Returns:
        A compiled LangGraph CompiledGraph ready for invocation.
    """
    builder = StateGraph(dict)
    
    # Add nodes
    builder.add_node("extraction", extraction_node)
    builder.add_node("categorizer", categorizer_node)
    builder.add_node("retriever", retriever_node)
    builder.add_node("qa", qa_node)
    builder.add_node("summarizer", summarizer_node)
    
    # Add edges
    builder.add_edge(START, "extraction")
    builder.add_edge("extraction", "categorizer")
    
    # Conditional routing after categorizer
    builder.add_conditional_edges(
        "categorizer",
        route_after_categorizer,
        {
            "retriever": "retriever",
            "summarizer": "summarizer",
        }
    )
    
    # Q&A path
    builder.add_edge("retriever", "qa")
    builder.add_edge("qa", END)
    
    # Summary path
    builder.add_edge("summarizer", END)
    
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
