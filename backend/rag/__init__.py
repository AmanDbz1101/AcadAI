"""
Multi-Agent RAG System for Research Paper Assistant
====================================================
Unified LangGraph workflow following the Chat2Code pattern.

Public API:
    - get_agent(): Get the compiled LangGraph agent (lazy singleton)
    - AgentState: Pydantic state model for the workflow
    - PaperCategory: Type literal for paper categories
"""

# Lazy imports to avoid circular dependencies
def get_agent():
    """Get the compiled LangGraph agent (lazy singleton)."""
    from .graph import get_agent as _get_agent
    return _get_agent()

def build_graph():
    """Build and return the LangGraph."""
    from .graph import build_graph as _build_graph
    return _build_graph()

__all__ = [
    "get_agent",
    "build_graph",
]
