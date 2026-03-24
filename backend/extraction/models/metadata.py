"""
Metadata models for document processing.

These models represent extracted metadata from research papers,
focusing on title, abstract, and document structure.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


class SectionStats(BaseModel):
    """Section-wise statistics for elements."""
    formulas: int = Field(0, description="Number of formulas in section")
    tables: int = Field(0, description="Number of tables in section")
    figures: int = Field(0, description="Number of figures in section")
    text_blocks: int = Field(0, description="Number of text blocks in section")
    formula_ids: List[str] = Field(default_factory=list, description="IDs of formulas in section")
    table_ids: List[str] = Field(default_factory=list, description="IDs of tables in section")
    figure_ids: List[str] = Field(default_factory=list, description="IDs of figures in section")
    text_block_ids: List[str] = Field(default_factory=list, description="IDs of text blocks in section")


class SectionInfo(BaseModel):
    """Section information from document structure with hierarchical support."""
    original_name: str = Field(..., description="Section heading text")
    level: int = Field(ge=1, le=5, description="Section depth level 1-5")
    page_start: int = Field(ge=1, description="Starting page number")
    stats: Optional[SectionStats] = Field(None, description="Section-wise element statistics")
    sections: Optional[List['SectionInfo']] = Field(None, description="Nested subsections")


# Enable forward references for recursive model
SectionInfo.model_rebuild()


class GlobalStats(BaseModel):
    """Global document statistics."""
    total_formulas: int = Field(0, description="Total formula count")
    total_tables: int = Field(0, description="Total table count")
    total_figures: int = Field(0, description="Total figure count")
    total_text_blocks: int = Field(0, description="Total text block count")
    total_pages: int = Field(0, description="Total page count")
    total_sections: int = Field(0, description="Total section count")


class PaperInference(BaseModel):
    """Inferred paper properties."""
    paper_type: str = Field("Unknown", description="Paper type classification")
    difficulty: str = Field("medium", description="Reading difficulty: easy, medium, hard")
    math_heavy: bool = Field(False, description="Whether paper contains heavy math content")


class ExtractedMetadata(BaseModel):
    """
    Extracted metadata from research paper.
    
    Focuses on accurate extraction of title, abstract, and document structure.
    """
    
    # Core metadata fields
    title: Optional[str] = Field(None, description="Paper title")
    abstract: Optional[str] = Field(None, description="Paper abstract")
    keywords: List[str] = Field(default_factory=list, description="Paper keywords")
    sections: List[SectionInfo] = Field(default_factory=list, description="Document sections")
    
    # Document statistics
    global_stats: Optional[GlobalStats] = Field(None, description="Document statistics")
    
    # Inferred properties
    inference: Optional[PaperInference] = Field(None, description="Inferred paper properties")

    # Structured elements extracted from Docling (extensible for future element types)
    extracted_elements: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Element payloads keyed by type (text_blocks, tables, figures, formulas, ...)"
    )
    
    # Extraction metadata
    extraction_method: str = Field("docling+groq", description="Method used for extraction")
    fallback_used: bool = Field(False, description="Whether LLM fallback was used")
    confidence_score: Optional[float] = Field(None, ge=0, le=1, description="Extraction confidence")
    missing_fields: List[str] = Field(default_factory=list, description="Fields that couldn't be extracted")
    
    # Timestamps
    extracted_at: datetime = Field(default_factory=datetime.utcnow, description="Extraction timestamp")
    
    def get_field_coverage(self) -> float:
        """Calculate percentage of core fields that were extracted."""
        core_fields = ['title', 'abstract', 'sections', 'keywords']
        extracted = sum(1 for field in core_fields if getattr(self, field))
        return extracted / len(core_fields)
    
    def is_complete(self) -> bool:
        """Check if core fields are present."""
        return all([self.title, self.abstract, len(self.sections) > 0, len(self.keywords) > 0])


class ProcessedDocument(BaseModel):
    """
    Processed document with extracted metadata.
    
    Contains structured metadata extracted from the document.
    """
    
    # Reference to validated document
    document_id: UUID = Field(..., description="Reference to ValidatedDocument ID")
    
    # Extracted metadata
    metadata: ExtractedMetadata = Field(..., description="Extracted document metadata")
    
    # Processing information
    processing_time_seconds: float = Field(0, ge=0, description="Metadata extraction duration")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Processing timestamp")
    
    # Additional fields (for future modules)
    extracted_elements: List[Dict[str, Any]] = Field(default_factory=list, description="Tables, figures, formulas")
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat(),
        }
