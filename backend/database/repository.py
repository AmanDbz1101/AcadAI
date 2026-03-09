"""
Repository — data-access layer for document storage.

Provides high-level CRUD operations that the ingestion pipeline can call
without knowing about SQLAlchemy sessions directly.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.database.models import (
    DocumentRecord,
    FigureRecord,
    FormulaRecord,
    SectionRecord,
    TableRecord,
    TextBlockRecord,
)

logger = logging.getLogger(__name__)


class DocumentRepository:
    """CRUD operations for the research-paper document store."""

    def __init__(self, session: Session):
        self._session = session

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def get_document_by_id(self, document_id: str) -> Optional[DocumentRecord]:
        return self._session.get(DocumentRecord, document_id)

    def get_document_by_hash(self, pdf_hash: str) -> Optional[DocumentRecord]:
        return (
            self._session.query(DocumentRecord)
            .filter(DocumentRecord.pdf_hash == pdf_hash)
            .first()
        )

    def document_exists(self, pdf_hash: str) -> bool:
        return self.get_document_by_hash(pdf_hash) is not None

    def upsert_document(self, record: DocumentRecord) -> DocumentRecord:
        """Insert or replace a document record (keyed on pdf_hash)."""
        existing = self.get_document_by_hash(record.pdf_hash)
        if existing:
            logger.info(
                f"Document {record.pdf_hash[:8]}… already exists "
                f"(id={existing.id}), skipping re-ingestion."
            )
            return existing

        self._session.add(record)
        self._session.flush()
        logger.debug(f"Inserted document id={record.id}")
        return record

    def delete_document(self, document_id: str) -> bool:
        """Delete a document and all its child records (cascade)."""
        doc = self.get_document_by_id(document_id)
        if doc is None:
            return False
        self._session.delete(doc)
        self._session.flush()
        return True

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def bulk_insert_sections(self, sections: list[SectionRecord]) -> None:
        self._session.bulk_save_objects(sections)
        self._session.flush()

    def get_sections_for_document(
        self, document_id: str
    ) -> list[SectionRecord]:
        return (
            self._session.query(SectionRecord)
            .filter(SectionRecord.document_id == document_id)
            .order_by(SectionRecord.reading_order)
            .all()
        )

    # ------------------------------------------------------------------
    # Text blocks
    # ------------------------------------------------------------------

    def bulk_insert_text_blocks(self, blocks: list[TextBlockRecord]) -> None:
        self._session.bulk_save_objects(blocks)
        self._session.flush()

    def get_text_blocks_for_document(
        self, document_id: str, page_number: Optional[int] = None
    ) -> list[TextBlockRecord]:
        q = (
            self._session.query(TextBlockRecord)
            .filter(TextBlockRecord.document_id == document_id)
        )
        if page_number is not None:
            q = q.filter(TextBlockRecord.page_number == page_number)
        return q.order_by(TextBlockRecord.reading_order).all()

    def get_text_blocks_for_section(
        self, section_id: str
    ) -> list[TextBlockRecord]:
        return (
            self._session.query(TextBlockRecord)
            .filter(TextBlockRecord.section_id == section_id)
            .order_by(TextBlockRecord.reading_order)
            .all()
        )

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def bulk_insert_tables(self, tables: list[TableRecord]) -> None:
        self._session.bulk_save_objects(tables)
        self._session.flush()

    def get_tables_for_document(self, document_id: str) -> list[TableRecord]:
        return (
            self._session.query(TableRecord)
            .filter(TableRecord.document_id == document_id)
            .order_by(TableRecord.reading_order)
            .all()
        )

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    def bulk_insert_figures(self, figures: list[FigureRecord]) -> None:
        self._session.bulk_save_objects(figures)
        self._session.flush()

    def get_figures_for_document(self, document_id: str) -> list[FigureRecord]:
        return (
            self._session.query(FigureRecord)
            .filter(FigureRecord.document_id == document_id)
            .order_by(FigureRecord.reading_order)
            .all()
        )

    # ------------------------------------------------------------------
    # Formulas
    # ------------------------------------------------------------------

    def bulk_insert_formulas(self, formulas: list[FormulaRecord]) -> None:
        self._session.bulk_save_objects(formulas)
        self._session.flush()

    def get_formulas_for_document(
        self, document_id: str
    ) -> list[FormulaRecord]:
        return (
            self._session.query(FormulaRecord)
            .filter(FormulaRecord.document_id == document_id)
            .order_by(FormulaRecord.reading_order)
            .all()
        )

    # ------------------------------------------------------------------
    # Summary / queries useful for retrieval
    # ------------------------------------------------------------------

    def list_documents(self) -> list[DocumentRecord]:
        return (
            self._session.query(DocumentRecord)
            .order_by(DocumentRecord.created_at.desc())
            .all()
        )

    def get_document_stats(self, document_id: str) -> dict:
        """Return a summary dict useful for debugging / health checks."""
        doc = self.get_document_by_id(document_id)
        if doc is None:
            return {}
        return {
            "id": doc.id,
            "title": doc.title,
            "pages": doc.total_pages,
            "sections": doc.total_sections,
            "text_blocks": doc.total_text_blocks,
            "tables": doc.total_tables,
            "figures": doc.total_figures,
            "formulas": doc.total_formulas,
        }
