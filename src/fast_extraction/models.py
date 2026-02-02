"""
Pydantic models for fast extraction pipeline
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class DocumentStatus(str, Enum):
    """Document processing status"""
    PROCESSING = "processing"
    DOCLING_READY = "docling_ready"
    API_COMPLETE = "api_complete"
    FAILED = "failed"


class SectionStats(BaseModel):
    """Basic statistics per section"""
    formulas: int = 0
    tables: int = 0
    figures: int = 0
    text_blocks: int = 0


class SectionInfo(BaseModel):
    """Section information from heading classification"""
    original_name: str
    level: int = Field(ge=1, le=5, description="Section depth level 1-5")
    page_start: int = Field(ge=1, description="Starting page number")
    stats: SectionStats = Field(default_factory=SectionStats)


class GlobalStats(BaseModel):
    """Global document statistics"""
    total_formulas: int = 0
    total_tables: int = 0
    total_figures: int = 0
    total_text_blocks: int = 0
    total_pages: int = 0
    total_sections: int = 0


class PaperInference(BaseModel):
    """Paper classification"""
    paper_type: str = "Unknown"
    difficulty: str = "medium"
    math_heavy: bool = False


class HeadingClassificationOutput(BaseModel):
    """Structured output from Groq LLM for heading classification"""
    title: str = Field(description="The main paper title")
    abstract: str = Field(description="Paper abstract text")
    sections: List[SectionInfo] = Field(description="Main content sections only, exclude References/Acknowledgements/Appendix")


class SimpleMetadata(BaseModel):
    """Simple metadata for guide generation"""
    document_id: str
    paper_title: str
    abstract: str
    sections: List[SectionInfo]
    global_stats: GlobalStats
    inference: PaperInference


class DocumentRecord(BaseModel):
    """Database record for document tracking"""
    id: Optional[int] = None
    document_id: str
    pdf_hash: str
    title: str
    status: DocumentStatus
    docling_metadata_path: Optional[str] = None
    api_metadata_path: Optional[str] = None
    vectorstore_collection: Optional[str] = None
    created_at: Optional[datetime] = None
