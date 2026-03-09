"""
SQLAlchemy ORM models for storing Docling-extracted document data.

Tables
------
documents        – Top-level document record (one per PDF)
sections         – Section hierarchy extracted by Docling
text_blocks      – Every text element with page, bbox, section, label
document_tables  – Extracted tables with serialised cell data (JSONB)
document_figures – Extracted figures / pictures with bbox
document_formulas– Extracted formulas / equations
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, backref as sa_backref


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

class DocumentRecord(Base):
    """Top-level metadata for an ingested PDF."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True,
        comment="UUID assigned by ingestion pipeline (matches document_id in existing pipeline)"
    )
    pdf_path: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True,
                                          comment="SHA-256 for deduplication")
    filename: Mapped[str] = mapped_column(String(512), nullable=False)

    # Metadata extracted by LLM
    title: Mapped[Optional[str]] = mapped_column(Text)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    paper_type: Mapped[Optional[str]] = mapped_column(String(64))
    difficulty: Mapped[Optional[str]] = mapped_column(String(16))
    math_heavy: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Aggregate statistics
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    total_sections: Mapped[int] = mapped_column(Integer, default=0)
    total_text_blocks: Mapped[int] = mapped_column(Integer, default=0)
    total_tables: Mapped[int] = mapped_column(Integer, default=0)
    total_figures: Mapped[int] = mapped_column(Integer, default=0)
    total_formulas: Mapped[int] = mapped_column(Integer, default=0)

    extraction_method: Mapped[str] = mapped_column(String(64), default="docling")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())

    # Relationships
    sections: Mapped[list["SectionRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    text_blocks: Mapped[list["TextBlockRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    tables: Mapped[list["TableRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    figures: Mapped[list["FigureRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    formulas: Mapped[list["FormulaRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

class SectionRecord(Base):
    """One row per section/subsection detected by Docling."""

    __tablename__ = "sections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True,
                                    comment="section_id generated during detection")
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False,
                                       comment="Hierarchy depth: 1=top-level")
    numbering: Mapped[Optional[str]] = mapped_column(String(64),
                                                      comment="e.g. '3.2.1'")
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("sections.id", ondelete="SET NULL")
    )

    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[Optional[int]] = mapped_column(Integer)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Typography hints from Docling
    font_size: Mapped[Optional[float]] = mapped_column(Float)
    is_bold: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Bounding box of the heading element itself
    bbox_l: Mapped[Optional[float]] = mapped_column(Float)
    bbox_t: Mapped[Optional[float]] = mapped_column(Float)
    bbox_r: Mapped[Optional[float]] = mapped_column(Float)
    bbox_b: Mapped[Optional[float]] = mapped_column(Float)
    bbox_coord_origin: Mapped[Optional[str]] = mapped_column(
        String(16), default="BOTTOMLEFT",
        comment="Docling uses BOTTOMLEFT origin by default"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())

    # Relationships
    document: Mapped["DocumentRecord"] = relationship(back_populates="sections")
    children: Mapped[list["SectionRecord"]] = relationship(
        "SectionRecord",
        primaryjoin="SectionRecord.parent_id == SectionRecord.id",
        foreign_keys="SectionRecord.parent_id",
        backref=sa_backref("parent", remote_side="SectionRecord.id"),
        lazy="select",
    )
    text_blocks: Mapped[list["TextBlockRecord"]] = relationship(
        back_populates="section"
    )
    tables: Mapped[list["TableRecord"]] = relationship(back_populates="section")
    figures: Mapped[list["FigureRecord"]] = relationship(back_populates="section")
    formulas: Mapped[list["FormulaRecord"]] = relationship(back_populates="section")


# ---------------------------------------------------------------------------
# Text Blocks
# ---------------------------------------------------------------------------

class TextBlockRecord(Base):
    """
    Every text-level element extracted by Docling (paragraphs, list items,
    section headers, captions, footnotes, page headers/footers, etc.).
    
    This is the primary table for the retrieval system — it stores full
    positional, structural, and content data for every text element.
    """

    __tablename__ = "text_blocks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    section_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("sections.id", ondelete="SET NULL"),
        comment="Section this block belongs to (NULL if none detected)"
    )

    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="Docling element label: text, section_header, list_item, caption, footnote, …"
    )

    # Position
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Bounding box (Docling BOTTOMLEFT-origin coordinates)
    bbox_l: Mapped[Optional[float]] = mapped_column(Float, comment="Left edge")
    bbox_t: Mapped[Optional[float]] = mapped_column(Float, comment="Top edge")
    bbox_r: Mapped[Optional[float]] = mapped_column(Float, comment="Right edge")
    bbox_b: Mapped[Optional[float]] = mapped_column(Float, comment="Bottom edge")
    bbox_coord_origin: Mapped[Optional[str]] = mapped_column(String(16), default="BOTTOMLEFT")

    # Font / typography
    font_name: Mapped[Optional[str]] = mapped_column(String(128))
    font_size: Mapped[Optional[float]] = mapped_column(Float)
    is_bold: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_italic: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Hierarchy context (denormalized for query performance)
    section_title: Mapped[Optional[str]] = mapped_column(Text,
                                                          comment="Title of containing section")
    section_level: Mapped[Optional[int]] = mapped_column(Integer,
                                                          comment="Depth level of containing section")
    section_path: Mapped[Optional[str]] = mapped_column(Text,
                                                         comment="Full path e.g. '3 > 3.2 > 3.2.1'")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())

    # Relationships
    document: Mapped["DocumentRecord"] = relationship(back_populates="text_blocks")
    section: Mapped[Optional["SectionRecord"]] = relationship(
        back_populates="text_blocks"
    )


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class TableRecord(Base):
    """Extracted tables with full cell data serialised as JSONB."""

    __tablename__ = "document_tables"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    section_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("sections.id", ondelete="SET NULL")
    )

    caption: Mapped[Optional[str]] = mapped_column(Text)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Bounding box
    bbox_l: Mapped[Optional[float]] = mapped_column(Float)
    bbox_t: Mapped[Optional[float]] = mapped_column(Float)
    bbox_r: Mapped[Optional[float]] = mapped_column(Float)
    bbox_b: Mapped[Optional[float]] = mapped_column(Float)
    bbox_coord_origin: Mapped[Optional[str]] = mapped_column(String(16), default="BOTTOMLEFT")

    # Dimensions
    row_count: Mapped[Optional[int]] = mapped_column(Integer)
    col_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Full cell data as JSON (list of rows, each row is a list of cell strings)
    table_data: Mapped[Optional[dict]] = mapped_column(JSONB,
                                                        comment="Serialised table rows/columns")

    # Section context (denormalized)
    section_title: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())

    document: Mapped["DocumentRecord"] = relationship(back_populates="tables")
    section: Mapped[Optional["SectionRecord"]] = relationship(back_populates="tables")


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

class FigureRecord(Base):
    """Extracted figures / pictures with bounding box and caption."""

    __tablename__ = "document_figures"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    section_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("sections.id", ondelete="SET NULL")
    )

    caption: Mapped[Optional[str]] = mapped_column(Text)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Bounding box
    bbox_l: Mapped[Optional[float]] = mapped_column(Float)
    bbox_t: Mapped[Optional[float]] = mapped_column(Float)
    bbox_r: Mapped[Optional[float]] = mapped_column(Float)
    bbox_b: Mapped[Optional[float]] = mapped_column(Float)
    bbox_coord_origin: Mapped[Optional[str]] = mapped_column(String(16), default="BOTTOMLEFT")

    section_title: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())

    document: Mapped["DocumentRecord"] = relationship(back_populates="figures")
    section: Mapped[Optional["SectionRecord"]] = relationship(back_populates="figures")


# ---------------------------------------------------------------------------
# Formulas
# ---------------------------------------------------------------------------

class FormulaRecord(Base):
    """Extracted mathematical formulas / equations."""

    __tablename__ = "document_formulas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    section_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("sections.id", ondelete="SET NULL")
    )

    content: Mapped[Optional[str]] = mapped_column(Text,
                                                    comment="LaTeX or plain text representation")
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Bounding box
    bbox_l: Mapped[Optional[float]] = mapped_column(Float)
    bbox_t: Mapped[Optional[float]] = mapped_column(Float)
    bbox_r: Mapped[Optional[float]] = mapped_column(Float)
    bbox_b: Mapped[Optional[float]] = mapped_column(Float)
    bbox_coord_origin: Mapped[Optional[str]] = mapped_column(String(16), default="BOTTOMLEFT")

    section_title: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())

    document: Mapped["DocumentRecord"] = relationship(back_populates="formulas")
    section: Mapped[Optional["SectionRecord"]] = relationship(back_populates="formulas")
