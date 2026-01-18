"""
Pydantic models for metadata extraction.

This module defines the strict data schemas for all stages of metadata extraction.
All models enforce validation rules to ensure data quality.
"""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, validator


class SectionStats(BaseModel):
    """Statistics for elements within a section."""
    
    formulas: int = Field(default=0, ge=0, description="Number of formulas in section")
    tables: int = Field(default=0, ge=0, description="Number of tables in section")
    figures: int = Field(default=0, ge=0, description="Number of figures in section")
    text_blocks: int = Field(default=0, ge=0, description="Number of text blocks in section")
    
    # Element IDs for each type
    formula_ids: List[str] = Field(default_factory=list, description="List of formula element IDs")
    table_ids: List[str] = Field(default_factory=list, description="List of table element IDs")
    figure_ids: List[str] = Field(default_factory=list, description="List of figure element IDs")
    text_block_ids: List[str] = Field(default_factory=list, description="List of text block element IDs")


class SectionMetadata(BaseModel):
    """Metadata for a single section in the paper."""
    
    original_name: str = Field(..., description="Original section title from document")
    level: int = Field(..., ge=1, le=5, description="Section depth (1=top-level)")
    page_start: int = Field(..., ge=1, description="First page where section appears")
    stats: SectionStats = Field(default_factory=SectionStats)
    
    @validator('original_name')
    def validate_name(cls, v):
        """Ensure section name is not empty."""
        if not v or not v.strip():
            raise ValueError("Section name cannot be empty")
        return v.strip()


class GlobalStats(BaseModel):
    """Global statistics across entire paper."""
    
    total_formulas: int = Field(default=0, ge=0)
    total_tables: int = Field(default=0, ge=0)
    total_figures: int = Field(default=0, ge=0)
    total_text_blocks: int = Field(default=0, ge=0)
    total_pages: int = Field(default=0, ge=1)
    total_sections: int = Field(default=0, ge=0)


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
    difficulty: Literal["easy", "medium", "hard"] = Field(
        description="Reading difficulty: easy, medium, or hard"
    )
    math_heavy: bool = Field(
        description="Whether the paper is math-heavy"
    )


class PaperMetadata(BaseModel):
    """Complete metadata for a research paper."""
    
    document_id: str = Field(..., description="Unique identifier for the paper")
    paper_title: str = Field(..., description="Title of the research paper")
    abstract: str = Field(default="", description="Paper abstract")
    sections: List[SectionMetadata] = Field(default_factory=list)
    global_stats: GlobalStats = Field(default_factory=GlobalStats)
    inference: PaperInference
    
    @validator('paper_title')
    def validate_title(cls, v):
        """Ensure title is not empty."""
        if not v or not v.strip():
            raise ValueError("Paper title cannot be empty")
        return v.strip()
    
    def model_dump_json(self, **kwargs):
        """Override to ensure clean JSON output."""
        return super().model_dump_json(indent=2, exclude_none=True, **kwargs)


class QdrantPoint(BaseModel):
    """Representation of a Qdrant point payload."""
    
    id: str
    page_number: int
    category: str
    page_content: str = ""
    element_id: Optional[str] = None
    parent_id: Optional[str] = None
    coordinates: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        extra = "allow"


class DocumentGroup(BaseModel):
    """Grouped and ordered points for a single document."""
    
    document_id: str
    points: List[QdrantPoint]
    
    @property
    def sorted_points(self) -> List[QdrantPoint]:
        """Return points sorted by page number."""
        return sorted(self.points, key=lambda p: p.page_number)
