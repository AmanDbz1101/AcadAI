"""
DB Ingestion Pipeline.

Takes the output of the existing extraction pipeline (ValidatedDocument +
ProcessedDocument + SectionDetectionResult) together with a fresh
DoclingRichResult and persists everything to PostgreSQL.

This pipeline is called *after* the existing extraction pipeline completes,
so it is purely additive — it never replaces or modifies the existing JSON
output system.

Usage
-----
::

    from backend.extraction.pipelines.db_ingestion_pipeline import DBIngestionPipeline

    pipeline = DBIngestionPipeline()
    pipeline.ingest(
        pdf_path=Path("paper.pdf"),
        document_id="<uuid from existing pipeline>",
        processed_doc=processed_doc,        # from MetadataExtractionPipeline
        hierarchy_result=hierarchy_result,  # from SectionHierarchyPipeline (optional)
    )
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from backend.database.connection import DatabaseConnection, get_db_connection
from backend.database.models import (
    DocumentRecord,
    FigureRecord,
    FormulaRecord,
    SectionRecord,
    TableRecord,
    TextBlockRecord,
)
from backend.database.repository import DocumentRepository
from backend.extraction.app.docling_rich_extractor import (
    DoclingRichExtractor,
    DoclingRichResult,
    RichFigureData,
    RichFormulaData,
    RichSectionData,
    RichTableData,
    RichTextBlock,
)
from backend.extraction.models.metadata import ProcessedDocument
from backend.extraction.models.section_hierarchy import SectionDetectionResult

logger = logging.getLogger(__name__)


class DBIngestionPipeline:
    """
    Orchestrates Docling-enhanced extraction → PostgreSQL storage.

    The pipeline:
    1. Runs :class:`DoclingRichExtractor` on the PDF (or reuses a cached result)
    2. Converts rich dataclasses → SQLAlchemy ORM records
    3. Enriches records with metadata from the existing pipeline (title,
       abstract, paper_type, section hierarchy from SectionDetectionResult)
    4. Persists everything via :class:`DocumentRepository`
    """

    def __init__(
        self,
        db_connection: Optional[DatabaseConnection] = None,
        rich_extractor: Optional[DoclingRichExtractor] = None,
    ):
        self._db = db_connection or get_db_connection()
        self._db.create_tables()
        self._extractor = rich_extractor or DoclingRichExtractor(
            extract_tables=True,
            extract_pictures=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        pdf_path: Path,
        document_id: str,
        processed_doc: Optional[ProcessedDocument] = None,
        hierarchy_result: Optional[SectionDetectionResult] = None,
        rich_result: Optional[DoclingRichResult] = None,
        skip_if_exists: bool = True,
    ) -> str:
        """
        Ingest a PDF into the database.

        Parameters
        ----------
        pdf_path:
            Path to the original PDF.
        document_id:
            UUID string from the existing ingestion pipeline (must match).
        processed_doc:
            Output of :class:`~backend.extraction.pipelines.metadata_pipeline.MetadataExtractionPipeline`.
            Used to enrich the document record with title, abstract, etc.
        hierarchy_result:
            Output of :class:`~backend.extraction.pipelines.section_hierarchy_pipeline.SectionHierarchyPipeline`.
            When provided, its section IDs are used to correlate section records.
        rich_result:
            Pre-computed :class:`DoclingRichResult`.  If *None*, the extractor
            is run fresh.
        skip_if_exists:
            If *True* (default) and the document hash already exists in the DB,
            return immediately without re-processing.

        Returns
        -------
        str
            The document ID that was stored.
        """
        pdf_path = Path(pdf_path)

        with self._db.session() as session:
            repo = DocumentRepository(session)

            # --- Run rich extraction if not already done ---
            if rich_result is None:
                rich_result = self._extractor.extract(pdf_path)

            # --- Check for duplicates ---
            if skip_if_exists and repo.document_exists(rich_result.pdf_hash):
                logger.info(
                    "Document %s already in DB (hash=%s…), skipping.",
                    pdf_path.name,
                    rich_result.pdf_hash[:8],
                )
                existing = repo.get_document_by_hash(rich_result.pdf_hash)
                return existing.id

            # --- Build document record ---
            meta = processed_doc.metadata if processed_doc else None
            inference = meta.inference if meta else None

            doc_record = DocumentRecord(
                id=document_id,
                pdf_path=str(pdf_path),
                pdf_hash=rich_result.pdf_hash,
                filename=rich_result.filename,
                title=meta.title if meta else None,
                abstract=meta.abstract if meta else None,
                paper_type=inference.paper_type if inference else None,
                difficulty=inference.difficulty if inference else None,
                math_heavy=inference.math_heavy if inference else None,
                total_pages=rich_result.total_pages,
                total_sections=len(rich_result.sections),
                total_text_blocks=len(rich_result.text_blocks),
                total_tables=len(rich_result.tables),
                total_figures=len(rich_result.figures),
                total_formulas=len(rich_result.formulas),
                extraction_method=meta.extraction_method if meta else "docling",
            )

            repo.upsert_document(doc_record)

            # --- Persist sections ---
            section_records = [
                self._build_section_record(s, document_id)
                for s in rich_result.sections
            ]
            repo.bulk_insert_sections(section_records)

            # --- Persist text blocks ---
            text_records = [
                self._build_text_block_record(b, document_id)
                for b in rich_result.text_blocks
            ]
            repo.bulk_insert_text_blocks(text_records)

            # --- Persist tables ---
            table_records = [
                self._build_table_record(t, document_id)
                for t in rich_result.tables
            ]
            repo.bulk_insert_tables(table_records)

            # --- Persist figures ---
            figure_records = [
                self._build_figure_record(f, document_id)
                for f in rich_result.figures
            ]
            repo.bulk_insert_figures(figure_records)

            # --- Persist formulas ---
            formula_records = [
                self._build_formula_record(fm, document_id)
                for fm in rich_result.formulas
            ]
            repo.bulk_insert_formulas(formula_records)

            logger.info(
                "Ingested document %s: %d sections, %d text blocks, "
                "%d tables, %d figures, %d formulas.",
                document_id,
                len(section_records),
                len(text_records),
                len(table_records),
                len(figure_records),
                len(formula_records),
            )

        return document_id

    # ------------------------------------------------------------------
    # ORM record builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_section_record(s: RichSectionData, doc_id: str) -> SectionRecord:
        return SectionRecord(
            id=s.section_id,
            document_id=doc_id,
            title=s.title,
            level=s.level,
            numbering=s.numbering,
            parent_id=s.parent_id,
            page_start=s.page_start,
            page_end=s.page_end,
            reading_order=s.reading_order,
            font_size=s.font_size,
            is_bold=s.is_bold,
            bbox_l=s.bbox.l if s.bbox else None,
            bbox_t=s.bbox.t if s.bbox else None,
            bbox_r=s.bbox.r if s.bbox else None,
            bbox_b=s.bbox.b if s.bbox else None,
            bbox_coord_origin=s.bbox.coord_origin if s.bbox else None,
        )

    @staticmethod
    def _build_text_block_record(b: RichTextBlock, doc_id: str) -> TextBlockRecord:
        return TextBlockRecord(
            id=b.block_id,
            document_id=doc_id,
            section_id=b.section_id,
            content=b.content,
            label=b.label,
            page_number=b.page_number,
            reading_order=b.reading_order,
            bbox_l=b.bbox.l if b.bbox else None,
            bbox_t=b.bbox.t if b.bbox else None,
            bbox_r=b.bbox.r if b.bbox else None,
            bbox_b=b.bbox.b if b.bbox else None,
            bbox_coord_origin=b.bbox.coord_origin if b.bbox else None,
            font_name=b.font_name,
            font_size=b.font_size,
            is_bold=b.is_bold,
            is_italic=b.is_italic,
            section_title=b.section_title,
            section_level=b.section_level,
            section_path=b.section_path,
        )

    @staticmethod
    def _build_table_record(t: RichTableData, doc_id: str) -> TableRecord:
        return TableRecord(
            id=t.table_id,
            document_id=doc_id,
            section_id=t.section_id,
            caption=t.caption,
            page_number=t.page_number,
            reading_order=t.reading_order,
            bbox_l=t.bbox.l if t.bbox else None,
            bbox_t=t.bbox.t if t.bbox else None,
            bbox_r=t.bbox.r if t.bbox else None,
            bbox_b=t.bbox.b if t.bbox else None,
            bbox_coord_origin=t.bbox.coord_origin if t.bbox else None,
            row_count=t.row_count,
            col_count=t.col_count,
            table_data=t.table_data,
            section_title=t.section_title,
        )

    @staticmethod
    def _build_figure_record(f: RichFigureData, doc_id: str) -> FigureRecord:
        return FigureRecord(
            id=f.figure_id,
            document_id=doc_id,
            section_id=f.section_id,
            caption=f.caption,
            page_number=f.page_number,
            reading_order=f.reading_order,
            bbox_l=f.bbox.l if f.bbox else None,
            bbox_t=f.bbox.t if f.bbox else None,
            bbox_r=f.bbox.r if f.bbox else None,
            bbox_b=f.bbox.b if f.bbox else None,
            bbox_coord_origin=f.bbox.coord_origin if f.bbox else None,
            section_title=f.section_title,
        )

    @staticmethod
    def _build_formula_record(fm: RichFormulaData, doc_id: str) -> FormulaRecord:
        return FormulaRecord(
            id=fm.formula_id,
            document_id=doc_id,
            section_id=fm.section_id,
            content=fm.content,
            page_number=fm.page_number,
            reading_order=fm.reading_order,
            bbox_l=fm.bbox.l if fm.bbox else None,
            bbox_t=fm.bbox.t if fm.bbox else None,
            bbox_r=fm.bbox.r if fm.bbox else None,
            bbox_b=fm.bbox.b if fm.bbox else None,
            bbox_coord_origin=fm.bbox.coord_origin if fm.bbox else None,
            section_title=fm.section_title,
        )
