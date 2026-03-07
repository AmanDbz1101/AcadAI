"""
Research Paper Assistant - Agent States
========================================
Pydantic state models for the unified LangGraph workflow.

Follows the Chat2Code pattern: clean, type-safe state management.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Category literals
# ---------------------------------------------------------------------------
PaperCategory = Literal[
    "ORIGINAL_RESEARCH",
    "SURVEY_REVIEW",
    "SYSTEM_ENGINEERING",
    "THEORETICAL",
    "BENCHMARK_DATASET",
]

Confidence = Literal["HIGH", "MEDIUM", "LOW"]


# ---------------------------------------------------------------------------
# Extraction Input/Output
# ---------------------------------------------------------------------------
class ExtractionInput(BaseModel):
    """Input for the extraction node."""
    pdf_path: str = Field(description="Path to the PDF file to extract")
    force_ocr: bool = Field(default=False, description="Force OCR even when text is selectable")


class ExtractionOutput(BaseModel):
    """Output from the extraction node."""
    document_id: str = Field(description="Unique document identifier")
    full_text: str = Field(description="Complete extracted text from the PDF")
    metadata: dict[str, Any] = Field(description="Extracted metadata (title, abstract, sections, stats)")
    hierarchy: dict[str, Any] = Field(description="Section hierarchy tree")
    files: dict[str, str] = Field(default_factory=dict, description="Paths to saved extraction artifacts")


# ---------------------------------------------------------------------------
# Retrieval Results
# ---------------------------------------------------------------------------
class RetrievalResult(BaseModel):
    """Single retrieval result from vector store."""
    content: str = Field(description="Retrieved text content")
    score: float = Field(description="Similarity score")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Result metadata (source, page, etc.)")


# ---------------------------------------------------------------------------
# Main Agent State
# ---------------------------------------------------------------------------
class AgentState(BaseModel):
    """
    Unified state for the Research Paper Assistant workflow.
    
    Workflow paths:
    1. Extraction only: pdf_path → extraction → categorization → END
    2. Q&A: pdf_path → extraction → categorization → retrieval → qa → END
    3. Summarization: pdf_path → extraction → categorization → summarization → END
    4. Reading Guide (ORIGINAL_RESEARCH): pdf_path → extraction → categorization → original_paper_guide → END
    """
    
    # === Input ===
    pdf_path: Optional[str] = Field(None, description="Path to PDF file (workflow entry point)")
    force_ocr: bool = Field(False, description="Force OCR regardless of text density")
    query: Optional[str] = Field(None, description="User query for Q&A (optional)")
    
    # === Extraction outputs ===
    document_id: Optional[str] = Field(None, description="Unique document identifier")
    full_text: Optional[str] = Field(None, description="Complete extracted text")
    title: Optional[str] = Field(None, description="Paper title")
    abstract: Optional[str] = Field(None, description="Paper abstract")
    sections: Optional[list[dict[str, Any]]] = Field(None, description="Extracted sections with stats")
    hierarchy: Optional[dict[str, Any]] = Field(None, description="Section hierarchy tree")
    extraction_files: Optional[dict[str, str]] = Field(None, description="Extraction artifact file paths")
    
    # === Categorization outputs ===
    category: Optional[PaperCategory] = Field(None, description="Paper category classification")
    confidence: Optional[Confidence] = Field(None, description="Classification confidence level")
    category_reasoning: Optional[str] = Field(None, description="Explanation for category choice")
    
    # === Retrieval outputs ===
    retrieval_results: Optional[list[RetrievalResult]] = Field(None, description="Vector search results")
    retrieval_query: Optional[str] = Field(None, description="Generated query for vector search")
    
    # === Q&A outputs ===
    answer: Optional[str] = Field(None, description="Answer to user query with citations")
    answer_confidence: Optional[Confidence] = Field(None, description="Confidence in the answer")
    
    # === Summarization outputs ===
    summary: Optional[str] = Field(None, description="Generated paper summary")
    key_contributions: Optional[list[str]] = Field(None, description="Main contributions extracted")
    
    # === Reading Guide outputs ===
    reading_guide: Optional[dict[str, Any]] = Field(None, description="Three-Pass Method reading guide (for ORIGINAL_RESEARCH)")
    guide_file_path: Optional[str] = Field(None, description="Path to saved reading guide JSON file")
    
    # === Control flow ===
    next_step: Optional[str] = Field(None, description="Next node to route to (for conditional edges)")
    
    # === Error tracking ===
    errors: list[str] = Field(default_factory=list, description="Accumulated errors during workflow")
    
    # === Extensibility ===
    model_config = ConfigDict(extra="allow")
