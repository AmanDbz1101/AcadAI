"""
Core document models for PDF ingestion and processing.

These models represent the validated, structured output from the ingestion pipeline,
providing a standardized interface for downstream modules (processing, chunking, retrieval).
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class DocumentStatus(str, Enum):
    """Processing status for document lifecycle tracking."""
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    EXTRACTING = "extracting"
    OCR_PROCESSING = "ocr_processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BoundingBox(BaseModel):
    """Bounding box coordinates for layout elements."""
    x0: float = Field(..., description="Left x-coordinate")
    y0: float = Field(..., description="Top y-coordinate")
    x1: float = Field(..., description="Right x-coordinate")
    y1: float = Field(..., description="Bottom y-coordinate")
    page_number: int = Field(..., ge=1, description="Page number (1-indexed)")

    @property
    def width(self) -> float:
        """Calculate bounding box width."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Calculate bounding box height."""
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        """Calculate bounding box area."""
        return self.width * self.height


class FontInfo(BaseModel):
    """Font information for text elements."""
    font_name: Optional[str] = Field(None, description="Font family name")
    font_size: Optional[float] = Field(None, ge=0, description="Font size in points")
    is_bold: bool = Field(False, description="Whether text is bold")
    is_italic: bool = Field(False, description="Whether text is italic")
    color: Optional[str] = Field(None, description="Text color (hex format)")


class LayoutSignals(BaseModel):
    """Layout and formatting signals for text elements."""
    bounding_box: Optional[BoundingBox] = Field(None, description="Element position")
    font_info: Optional[FontInfo] = Field(None, description="Font properties")
    reading_order: Optional[int] = Field(None, ge=0, description="Reading order index")
    column_number: Optional[int] = Field(None, ge=1, description="Column number in multi-column layout")
    is_header: bool = Field(False, description="Whether element is a header")
    is_footer: bool = Field(False, description="Whether element is a footer")
    line_spacing: Optional[float] = Field(None, ge=0, description="Line spacing")


class OCRMetadata(BaseModel):
    """Metadata about OCR processing."""
    was_ocr_applied: bool = Field(..., description="Whether OCR was used")
    ocr_engine: Optional[str] = Field(None, description="OCR engine name (e.g., 'RapidOCR')")
    confidence_score: Optional[float] = Field(None, ge=0, le=1, description="Overall OCR confidence")
    pages_ocr_processed: List[int] = Field(default_factory=list, description="Pages that underwent OCR")
    text_density_ratio: Optional[float] = Field(None, ge=0, description="Average text density (chars per page)")
    processing_time_seconds: Optional[float] = Field(None, ge=0, description="OCR processing duration")


class PageContent(BaseModel):
    """Content and metadata for a single page."""
    page_number: int = Field(..., ge=1, description="Page number (1-indexed)")
    text: str = Field(..., description="Extracted text content")
    layout_signals: Optional[LayoutSignals] = Field(None, description="Layout information")
    word_count: int = Field(0, ge=0, description="Number of words on page")
    char_count: int = Field(0, ge=0, description="Number of characters on page")
    has_images: bool = Field(False, description="Whether page contains images")
    has_tables: bool = Field(False, description="Whether page contains tables")
    has_formulas: bool = Field(False, description="Whether page contains mathematical formulas")

    @field_validator('word_count', mode='before')
    @classmethod
    def calculate_word_count(cls, v, info):
        """Auto-calculate word count if not provided."""
        if v == 0 and 'text' in info.data:
            return len(info.data['text'].split())
        return v

    @field_validator('char_count', mode='before')
    @classmethod
    def calculate_char_count(cls, v, info):
        """Auto-calculate character count if not provided."""
        if v == 0 and 'text' in info.data:
            return len(info.data['text'])
        return v


class ValidatedDocument(BaseModel):
    """
    Validated document object from PDF ingestion.
    
    This is the standardized output format that downstream modules consume.
    It contains raw PDF reference, extracted text, layout signals, and metadata.
    """
    
    # Identification
    document_id: UUID = Field(default_factory=uuid4, description="Unique document identifier")
    pdf_path: Path = Field(..., description="Path to original PDF file")
    pdf_hash: str = Field(..., description="SHA256 hash for deduplication")
    
    # Content
    pages: List[PageContent] = Field(..., description="Page-wise content with layout signals")
    full_text: str = Field("", description="Concatenated text from all pages")
    
    # Metadata
    page_count: int = Field(..., ge=1, description="Total number of pages")
    file_size_bytes: int = Field(..., ge=0, description="PDF file size in bytes")
    ocr_metadata: Optional[OCRMetadata] = Field(None, description="OCR processing information")
    
    # Processing tracking
    status: DocumentStatus = Field(DocumentStatus.COMPLETED, description="Processing status")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Ingestion timestamp")
    processing_time_seconds: float = Field(0, ge=0, description="Total processing duration")
    
    # Additional metadata (populated by downstream modules)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extensible metadata")
    
    # Cached Docling document object (excluded from serialization)
    docling_document: Optional[Any] = Field(default=None, exclude=True, description="Cached DoclingDocument from conversion")

    @field_validator('full_text', mode='before')
    @classmethod
    def generate_full_text(cls, v, info):
        """Auto-generate full_text from pages if not provided."""
        if not v and 'pages' in info.data:
            return "\n\n".join(page.text for page in info.data['pages'])
        return v

    @field_validator('page_count', mode='before')
    @classmethod
    def validate_page_count(cls, v, info):
        """Ensure page_count matches pages list."""
        if 'pages' in info.data:
            actual_count = len(info.data['pages'])
            if v != actual_count:
                return actual_count
        return v

    @property
    def total_word_count(self) -> int:
        """Calculate total word count across all pages."""
        return sum(page.word_count for page in self.pages)

    @property
    def total_char_count(self) -> int:
        """Calculate total character count across all pages."""
        return sum(page.char_count for page in self.pages)

    @property
    def average_text_density(self) -> float:
        """Calculate average text density (chars per page)."""
        return self.total_char_count / self.page_count if self.page_count > 0 else 0

    @property
    def requires_ocr(self) -> bool:
        """Determine if document likely needs OCR based on text density."""
        # Less than 50 characters per page suggests scanned/image PDF
        return self.average_text_density < 50

    def get_page(self, page_number: int) -> Optional[PageContent]:
        """Retrieve specific page by number."""
        for page in self.pages:
            if page.page_number == page_number:
                return page
        return None

    def get_text_range(self, start_page: int, end_page: int) -> str:
        """Extract text from page range (inclusive)."""
        text_parts = []
        for page in self.pages:
            if start_page <= page.page_number <= end_page:
                text_parts.append(page.text)
        return "\n\n".join(text_parts)

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            Path: str,
            UUID: str,
            datetime: lambda v: v.isoformat(),
        }
        use_enum_values = True
        arbitrary_types_allowed = True
