"""
Chunk data model — the single data contract
across all retrieval pipeline stages.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class Chunk(BaseModel):
    """
    A single indexable unit of document content.

    Carries full section context so that downstream consumers (indexer,
    retriever, evaluation) always know exactly where each piece of text
    came from within the paper's structure.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    chunk_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Globally unique identifier for this chunk",
    )
    document_id: str = Field(description="UUID of the parent document")

    # ── Content ─────────────────────────────────────────────────────────────
    content: str = Field(description="Raw text content of the chunk")
    token_count: int = Field(default=0, description="Estimated token count")
    chunk_index: int = Field(
        description="Zero-based index of this chunk within the document"
    )
    chunk_level: str = Field(
        default="coarse",
        description="Chunk granularity level ('fine' or 'coarse')",
    )

    # ── Section context ──────────────────────────────────────────────────────
    section_id: Optional[str] = Field(
        None, description="SectionNode.section_id from hierarchy.json"
    )
    section_title: str = Field(default="", description="Title of the containing section")
    section_level: int = Field(default=1, description="Heading depth (1 = top-level)")
    section_numbering: Optional[str] = Field(
        None, description="Dotted numbering string, e.g. '3.2.1'"
    )
    section_path: list[str] = Field(
        default_factory=list,
        description="Breadcrumb from root to this section, e.g. ['Model Architecture', 'Attention', 'Multi-Head Attention']",
    )
    parent_section_id: Optional[str] = Field(
        None, description="ID of the immediate parent SectionNode"
    )

    # ── Location ─────────────────────────────────────────────────────────────
    page_start: Optional[int] = Field(None, description="First page of the source section")
    page_end: Optional[int] = Field(None, description="Last page of the source section")

    # ── Element references ───────────────────────────────────────────────────
    element_ids: list[str] = Field(
        default_factory=list,
        description="Docling element IDs covered by this chunk (for cross-referencing)",
    )

    # ── Source provenance ────────────────────────────────────────────────────
    source_file: Optional[str] = Field(
        None, description="Relative path to the source file (_fulltext.txt or PDF)"
    )

    def to_payload(self) -> dict[str, Any]:
        """
        Serialise the chunk to a flat Qdrant point payload dict.

        Qdrant payloads must be JSON-serialisable; nested lists of strings
        are fine, but Pydantic models are not.
        """
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "content": self.content,
            "token_count": self.token_count,
            "chunk_index": self.chunk_index,
            "chunk_level": self.chunk_level,
            "section_id": self.section_id,
            "section_title": self.section_title,
            "section_level": self.section_level,
            "section_numbering": self.section_numbering,
            "section_path": self.section_path,
            "parent_section_id": self.parent_section_id,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "element_ids": self.element_ids,
            "source_file": self.source_file,
        }
