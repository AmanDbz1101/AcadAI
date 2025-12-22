"""
Pydantic models for Research Paper Metadata Extraction.

This module defines the structured data models used throughout the extraction pipeline.
"""

from pydantic import BaseModel, Field


class SectionMetadata(BaseModel):
    """Represents a section in the research paper.
    
    Attributes:
        original_name: The section name as it appears in the paper
        normalized_name: Canonical section name (None if no clear mapping)
        page_start: Page number where the section begins (1-indexed)
    """
    original_name: str = Field(description="Section name as it appears in the paper")
    normalized_name: str | None = Field(
        default=None,
        description="Normalized canonical section name"
    )
    page_start: int = Field(description="Starting page number (1-indexed)")


class PaperInference(BaseModel):
    """LLM-inferred properties about the research paper.
    
    Attributes:
        paper_type: Classification of paper (Survey, System, Theoretical, Empirical, etc.)
        difficulty: Reading difficulty (easy, medium, hard)
        math_heavy: Whether the paper contains heavy mathematical content
    """
    paper_type: str = Field(
        description="Type of paper: Survey, System, Theoretical, Empirical, etc."
    )
    difficulty: str = Field(
        description="Reading difficulty: easy, medium, or hard"
    )
    math_heavy: bool = Field(
        description="Whether the paper is math-heavy"
    )


class PaperMetadata(BaseModel):
    """Complete metadata for a research paper.
    
    This is the final output of the extraction pipeline.
    
    Attributes:
        title: Paper title
        abstract: Paper abstract
        sections: List of detected sections with metadata
        inference: LLM-inferred paper properties
    """
    title: str = Field(description="Paper title")
    abstract: str = Field(description="Paper abstract")
    sections: list[SectionMetadata] = Field(description="Detected sections")
    inference: PaperInference = Field(description="Inferred paper properties")
