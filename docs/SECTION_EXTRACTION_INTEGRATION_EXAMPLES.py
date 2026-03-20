"""
Integration examples showing how to use section extraction
in your RAG pipeline, API endpoints, and LangGraph workflow.
"""

# ============================================================================
# EXAMPLE 1: Using in API Endpoint (FastAPI)
# ============================================================================

from fastapi import FastAPI, HTTPException
from backend.rag.retrieval.section_query import (
    get_all_documents,
    get_introduction,
    get_conclusion,
    get_all_sections,
)

app = FastAPI()


@app.get("/papers")
def list_papers():
    """Get all papers in the database."""
    docs = get_all_documents()
    return {
        "count": len(docs),
        "papers": [
            {
                "id": doc["id"],
                "filename": doc["filename"],
                "title": doc["title"],
                "sections": doc["total_sections"],
            }
            for doc in docs
        ],
    }


@app.get("/papers/{paper_id}/sections/introduction")
def get_paper_introduction(paper_id: str):
    """Get introduction section from a paper."""
    intro = get_introduction(paper_id)
    if not intro["found"]:
        raise HTTPException(status_code=404, detail="Introduction not found")

    return {
        "section": "introduction",
        "title": intro["title"],
        "pages": f"{intro['page_start']}-{intro['page_end']}",
        "length": intro["content_length"],
        "content": intro["content"],
    }


@app.get("/papers/{paper_id}/sections/conclusion")
def get_paper_conclusion(paper_id: str):
    """Get conclusion section from a paper."""
    conclusion = get_conclusion(paper_id)
    if not conclusion["found"]:
        raise HTTPException(status_code=404, detail="Conclusion not found")

    return {
        "section": "conclusion",
        "title": conclusion["title"],
        "pages": f"{conclusion['page_start']}-{conclusion['page_end']}",
        "length": conclusion["content_length"],
        "content": conclusion["content"],
    }


@app.get("/papers/{paper_id}/sections")
def get_paper_sections(paper_id: str, sections: str = "all"):
    """
    Get multiple sections from a paper.

    Args:
        paper_id: UUID of the paper
        sections: Comma-separated section names (e.g., "introduction,methods,conclusion")
                 or "all" for all available sections
    """
    if sections == "all":
        section_dict = get_all_sections(paper_id)
    else:
        # Parse requested sections
        requested = sections.split(",")
        keywords_map = {
            "abstract": ["abstract"],
            "introduction": ["introduction", "intro"],
            "methods": ["method", "methodology"],
            "results": ["result", "experiment"],
            "conclusion": ["conclusion", "future work"],
        }

        requested_keywords = {}
        for req_section in requested:
            if req_section in keywords_map:
                requested_keywords[req_section] = keywords_map[req_section]

        section_dict = get_all_sections(paper_id, requested_keywords)

    # Return findings with summaries
    results = {}
    for name, section in section_dict.items():
        if section["found"]:
            results[name] = {
                "found": True,
                "title": section["title"],
                "level": section["level"],
                "pages": f"{section['page_start']}-{section['page_end']}" if section['page_end'] else str(section['page_start']),
                "length": section["content_length"],
                "preview": section["content"][:300] + "..."
                if section["content_length"] > 300
                else section["content"],
                # "content": section["content"],  # Uncomment to get full content
            }
        else:
            results[name] = {"found": False}

    return results


# ============================================================================
# EXAMPLE 2: Using in LangGraph Node (State Machine)
# ============================================================================

from langgraph.graph import StateGraph, StateDict
from typing import Annotated, Dict, Any
from backend.rag.retrieval.section_query import get_introduction, get_conclusion


class PaperAnalysisState(StateDict):
    """State for multi-step paper analysis."""

    document_id: str
    introduction: Dict[str, Any]
    conclusion: Dict[str, Any]
    analysis_result: str
    error: str


def extract_introduction_node(state: PaperAnalysisState) -> PaperAnalysisState:
    """Extract introduction section."""
    state["introduction"] = get_introduction(state["document_id"])
    return state


def extract_conclusion_node(state: PaperAnalysisState) -> PaperAnalysisState:
    """Extract conclusion section."""
    state["conclusion"] = get_conclusion(state["document_id"])
    return state


def analyze_paper_contribution_node(state: PaperAnalysisState) -> PaperAnalysisState:
    """Analyze paper contribution using LLM and section content."""
    try:
        intro = state.get("introduction")
        conclusion = state.get("conclusion")

        if not intro or not intro["found"]:
            state["error"] = "Could not extract introduction"
            return state

        if not conclusion or not conclusion["found"]:
            state["error"] = "Could not extract conclusion"
            return state

        # Use with LLM (pseudo-code)
        prompt = f"""
Based on the introduction and conclusion of a research paper,
summarize the main contribution and impact:

INTRODUCTION:
{intro['content'][:1000]}

CONCLUSION:
{conclusion['content'][:1000]}

Summarize the paper's contribution in 2-3 sentences.
"""

        # Call your LLM
        # state["analysis_result"] = llm.invoke(prompt)
        state["analysis_result"] = "Analysis placeholder"

    except Exception as e:
        state["error"] = str(e)

    return state


# Build graph
def build_paper_analysis_graph():
    """Create LangGraph workflow for paper analysis."""
    graph = StateGraph(PaperAnalysisState)

    # Add nodes
    graph.add_node("extract_intro", extract_introduction_node)
    graph.add_node("extract_conclusion", extract_conclusion_node)
    graph.add_node("analyze", analyze_paper_contribution_node)

    # Add edges
    graph.add_edge("__start__", "extract_intro")
    graph.add_edge("extract_intro", "extract_conclusion")
    graph.add_edge("extract_conclusion", "analyze")
    graph.add_edge("analyze", "__end__")

    return graph.compile()


# Usage:
# workflow = build_paper_analysis_graph()
# result = workflow.invoke({
#     "document_id": "2f5cdbf0-49e0-46af-8bdc-d861443d92c7"
# })
# print(result["analysis_result"])


# ============================================================================
# EXAMPLE 3: Using with RAG Retrieval Pipeline
# ============================================================================

from backend.rag.retrieval.pipeline import RetrievalPipeline
from backend.rag.retrieval.section_query import get_all_sections


def retrieve_with_section_context(
    document_id: str,
    query: str,
    focus_section: str = None,
):
    """Retrieve information with optional section context."""

    pipeline = RetrievalPipeline(enable_reranking=True)

    # Get section context if requested
    section_context = ""
    if focus_section:
        sections = get_all_sections(
            document_id, {focus_section: [focus_section.lower()]}
        )
        if sections[focus_section]["found"]:
            section_context = f"\nContext from {focus_section} section:\n"
            section_context += sections[focus_section]["content"][:500]

    # Run retrieval
    results = pipeline.query(
        query=query,
        document_id=document_id,
        top_k=10,
        top_n=5,
    )

    return {
        "query": query,
        "section_focus": focus_section,
        "section_context": section_context,
        "results": [
            {
                "score": r.score,
                "content": r.content[:300],
                "section": r.metadata.get("section_title", "N/A"),
            }
            for r in results
        ],
    }


# Usage:
# answer = retrieve_with_section_context(
#     document_id="2f5cdbf0-49e0-46af-8bdc-d861443d92c7",
#     query="What are the key results?",
#     focus_section="results"  # Or "methods", "conclusion", etc.
# )


# ============================================================================
# EXAMPLE 4: Building a Question-Answering System with Sections
# ============================================================================

from backend.rag.retrieval.section_query import get_introduction, get_conclusion


class SectionAwareQASystem:
    """Q&A system that routes questions to appropriate sections."""

    def __init__(self, document_id: str):
        self.document_id = document_id
        self._load_sections()

    def _load_sections(self):
        """Pre-load relevant sections."""
        self.intro = get_introduction(self.document_id)
        self.conclusion = get_conclusion(self.document_id)

    def route_question(self, query: str) -> Dict[str, Any]:
        """Route question to most relevant section."""

        query_lower = query.lower()

        # Simple routing logic
        if any(
            word in query_lower
            for word in ["what", "problem", "motivation", "background"]
        ):
            section = self.intro
            section_name = "introduction"
        elif any(
            word in query_lower
            for word in ["conclusion", "future", "impact", "limitation"]
        ):
            section = self.conclusion
            section_name = "conclusion"
        else:
            # Default to introduction
            section = self.intro
            section_name = "introduction"

        return {
            "query": query,
            "routed_to": section_name,
            "section_title": section["title"] if section["found"] else None,
            "context": section["content"][:1000] if section["found"] else None,
        }

    def answer_question(self, query: str) -> Dict[str, Any]:
        """Answer question using section context."""

        routing = self.route_question(query)

        # In a real system, you would:
        # 1. Use the routing result as LLM context
        # 2. Retrieve additional relevant chunks
        # 3. Generate answer with citations

        return {
            "question": query,
            "routed_section": routing["routed_to"],
            "section_content": routing["context"],
            # "answer": llm.generate(query, routing["context"]),
        }


# Usage:
# qa = SectionAwareQASystem("2f5cdbf0-49e0-46af-8bdc-d861443d92c7")
# answer = qa.answer_question("What problem does this paper solve?")
# print(answer["section_content"])
# print(answer["answer"])


# ============================================================================
# EXAMPLE 5: Batch Processing Multiple Papers
# ============================================================================

from backend.rag.retrieval.section_query import (
    get_all_documents,
    get_introduction,
    get_conclusion,
)


def extract_all_paper_summaries():
    """Extract introduction and conclusion from all papers."""

    docs = get_all_documents()
    results = []

    for doc in docs:
        intro = get_introduction(doc["id"])
        conclusion = get_conclusion(doc["id"])

        results.append(
            {
                "filename": doc["filename"],
                "document_id": doc["id"],
                "intro_found": intro["found"],
                "intro_length": intro["content_length"],
                "conclusion_found": conclusion["found"],
                "conclusion_length": conclusion["content_length"],
                "intro_preview": intro["content"][:200] if intro["found"] else None,
                "conclusion_preview": (
                    conclusion["content"][:200] if conclusion["found"] else None
                ),
            }
        )

    return results


# Usage:
# summaries = extract_all_paper_summaries()
# for summary in summaries:
#     print(f"{summary['filename']}: intro={summary['intro_length']} chars, "
#           f"conclusion={summary['conclusion_length']} chars")


# ============================================================================
# EXAMPLE 6: Cache Section Extractions for Performance
# ============================================================================

from functools import lru_cache
from backend.rag.retrieval.section_query import get_introduction, get_conclusion


class CachedSectionExtractor:
    """Section extractor with caching for frequently accessed papers."""

    def __init__(self, cache_size: int = 100):
        self.cache_size = cache_size
        self._intro_cache = {}
        self._conclusion_cache = {}

    @lru_cache(maxsize=100)
    def get_intro_cached(self, document_id: str):
        """Get introduction with caching."""
        return get_introduction(document_id)

    @lru_cache(maxsize=100)
    def get_conclusion_cached(self, document_id: str):
        """Get conclusion with caching."""
        return get_conclusion(document_id)

    def get_sections_cached(self, document_id: str, sections: list):
        """Get multiple sections with caching."""
        from backend.rag.retrieval.section_query import get_all_sections

        result = {}
        for section in sections:
            if section == "introduction":
                result["introduction"] = self.get_intro_cached(document_id)
            elif section == "conclusion":
                result["conclusion"] = self.get_conclusion_cached(document_id)

        return result


# Usage:
# extractor = CachedSectionExtractor()
# intro = extractor.get_intro_cached("2f5cdbf0-49e0-46af-8bdc-d861443d92c7")
# # Second call returns from cache
# intro_again = extractor.get_intro_cached("2f5cdbf0-49e0-46af-8bdc-d861443d92c7")


if __name__ == "__main__":
    # Example: Batch extract all paper summaries
    print("Extracting all paper summaries...\n")

    summaries = extract_all_paper_summaries()
    for summary in summaries:
        print(f"📄 {summary['filename']}")
        print(f"   Introduction: {summary['intro_length']} chars")
        print(f"   Conclusion: {summary['conclusion_length']} chars")
        print()
