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
import os
import re
from pathlib import Path
from typing import Optional

from backend.extraction.persistence import PostgresPaperStore
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

import re
from typing import Any

try:
    from langsmith.run_helpers import traceable
except Exception:  # noqa: BLE001
    def traceable(*_args, **_kwargs):
        def _decorator(func):
            return func

        return _decorator

_TRACE_RUNNER_CACHE: dict[str, Any] = {}


def _safe_trace_stage_name(stage: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(stage).strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unknown"


def _trace_db_stage(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    safe_stage = _safe_trace_stage_name(stage)
    runner = _TRACE_RUNNER_CACHE.get(safe_stage)
    if runner is None:
        @traceable(name=f"db_ingest:{safe_stage}", run_type="chain")
        def _runner(event_payload: dict[str, Any]) -> dict[str, Any]:
            return event_payload

        runner = _runner
        _TRACE_RUNNER_CACHE[safe_stage] = runner

    return runner({"stage": stage, **payload})


class DBIngestionPipeline:
    """
    Orchestrates Docling-enhanced extraction → PostgreSQL storage.

    The pipeline:
    1. Runs :class:`DoclingRichExtractor` on the PDF (or reuses a cached result)
    2. Converts rich dataclasses → SQLAlchemy ORM records
    3. Enriches records with metadata from the existing pipeline (title,
       abstract, paper_type, section hierarchy from SectionDetectionResult)
    4. Persists everything via :class:`PostgresPaperStore`
    """

    def __init__(
        self,
        db_connection: Optional[object] = None,
        rich_extractor: Optional[DoclingRichExtractor] = None,
        postgres_dsn: Optional[str] = None,
    ):
        dsn = postgres_dsn or getattr(db_connection, "_url", None) or os.getenv("DATABASE_URL")
        if not dsn:
            host = os.getenv("PG_HOST", "localhost")
            port = os.getenv("PG_PORT", "5432")
            db = os.getenv("PG_DB", "research_agent")
            user = os.getenv("PG_USER", "postgres")
            pwd = os.getenv("PG_PASSWORD", "")
            if pwd:
                dsn = f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{db}"
            else:
                dsn = f"postgresql+psycopg://{user}@{host}:{port}/{db}"

        self._store = PostgresPaperStore(dsn)
        self._store.ensure_schema()
        self._extractor = rich_extractor or DoclingRichExtractor(
            extract_tables=True,
            extract_pictures=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @traceable(name="db_ingestion_pipeline", run_type="chain")


    def ingest(
        self,
        pdf_path: Path,
        document_id: str,
        processed_doc: Optional[ProcessedDocument] = None,
        hierarchy_result: Optional[SectionDetectionResult] = None,
        rich_result: Optional[DoclingRichResult] = None,
        full_text: Optional[str] = None,
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

        _trace_db_stage("start", {"pdf_path": str(pdf_path), "document_id": document_id})

        if rich_result is None:
            rich_result = self._extractor.extract(pdf_path)

        meta = processed_doc.metadata if processed_doc else None
        inference = meta.inference if meta else None

        metadata_json = {
            "filename": rich_result.filename,
            "total_pages": rich_result.total_pages,
            "total_sections": len(rich_result.sections),
            "total_text_blocks": len(rich_result.text_blocks),
            "total_tables": len(rich_result.tables),
            "total_figures": len(rich_result.figures),
            "total_formulas": len(rich_result.formulas),
            "paper_type": inference.paper_type if inference else None,
            "difficulty": inference.difficulty if inference else None,
            "math_heavy": inference.math_heavy if inference else None,
            "hierarchy_available": bool(hierarchy_result),
            "extraction_method": meta.extraction_method if meta else "docling",
        }

        sections_payload = self._build_nested_sections(rich_result)
        extracted_elements = self._build_extracted_elements(rich_result, full_text=full_text)
        paper_name = (meta.title if meta and meta.title else pdf_path.stem).strip()

        persist_result = self._store.persist_extraction(
            paper_name=paper_name,
            title=meta.title if meta else None,
            abstract=meta.abstract if meta else None,
            pdf_hash=rich_result.pdf_hash,
            source_pdf_path=str(pdf_path),
            document_uuid=document_id,
            metadata_json=metadata_json,
            sections=sections_payload,
            extracted_elements=extracted_elements,
        )

        logger.info(
            "DB ingestion result for %s: stored=%s reason=%s paper_id=%s",
            document_id,
            persist_result.stored,
            persist_result.reason,
            persist_result.paper_id,
        )

        _trace_db_stage("completed", {
            "document_id": document_id,
            "stored": bool(persist_result.stored),
            "paper_id": persist_result.paper_id,
        })

        return str(persist_result.paper_id) if persist_result.paper_id is not None else document_id

    # ------------------------------------------------------------------
    # Payload builders for PostgresPaperStore
    # ------------------------------------------------------------------

    @staticmethod
    def _build_nested_sections(rich_result: DoclingRichResult) -> list[dict]:
        children: dict[Optional[str], list[RichSectionData]] = {}
        text_by_section: dict[str, list[str]] = {}
        table_by_section: dict[str, list[str]] = {}
        fig_by_section: dict[str, list[str]] = {}

        for b in rich_result.text_blocks:
            if b.section_id:
                text_by_section.setdefault(b.section_id, []).append(b.block_id)
        for t in rich_result.tables:
            if t.section_id:
                table_by_section.setdefault(t.section_id, []).append(t.table_id)
        for f in rich_result.figures:
            if f.section_id:
                fig_by_section.setdefault(f.section_id, []).append(f.figure_id)

        for s in rich_result.sections:
            children.setdefault(s.parent_id, []).append(s)

        for sibling_group in children.values():
            sibling_group.sort(key=lambda s: s.reading_order)

        def build_node(section: RichSectionData) -> dict:
            return {
                "original_name": section.title,
                "level": section.level,
                "page_start": section.page_start,
                "stats": {
                    "text_block_ids": text_by_section.get(section.section_id, []),
                    "table_ids": table_by_section.get(section.section_id, []),
                    "figure_ids": fig_by_section.get(section.section_id, []),
                },
                "sections": [build_node(ch) for ch in children.get(section.section_id, [])],
            }

        roots = children.get(None, [])
        if not roots:
            roots = sorted(
                [s for s in rich_result.sections if not s.parent_id],
                key=lambda s: s.reading_order,
            )
        return [build_node(s) for s in roots]

    @staticmethod
    def _build_extracted_elements(rich_result: DoclingRichResult, full_text: Optional[str] = None) -> dict:
        text_blocks = [
            {
                "id": b.block_id,
                "page": b.page_number,
                "text": b.content,
                "label": b.label,
                "section_id": b.section_id,
                "section_title": b.section_title,
                "section": b.section_title,
                "section_path": b.section_path,
            }
            for b in rich_result.text_blocks
        ]

        tables = [
            {
                "id": t.table_id,
                "page": t.page_number,
                "text": str(t.table_data) if t.table_data is not None else None,
                "markdown": None,
                "caption": t.caption,
                "section_id": t.section_id,
                "row_count": t.row_count,
                "col_count": t.col_count,
            }
            for t in rich_result.tables
        ]

        figures = [
            {
                "id": f.figure_id,
                "page": f.page_number,
                "caption": f.caption,
                "section_id": f.section_id,
            }
            for f in rich_result.figures
        ]

        references: list[dict] = []
        for b in rich_result.text_blocks:
            label = str(b.label or "").strip().lower()
            section_title = str(b.section_title or "").strip().lower()
            text = (b.content or "").strip()

            in_reference_section = (
                "reference" in section_title
                or "bibliograph" in section_title
                or "works cited" in section_title
            )
            is_reference_label = label in {"reference", "bibliography"}
            is_reference_text = DBIngestionPipeline._looks_like_reference_block(text)
            if not (in_reference_section or is_reference_label or is_reference_text):
                continue
            if not text:
                continue

            entries = DBIngestionPipeline._split_reference_entries(text)
            if not entries:
                entries = [text]

            for idx, entry in enumerate(entries):
                entry_text = (entry or "").strip()
                if not entry_text:
                    continue
                references.append(
                    {
                        "id": f"{b.block_id}_ref_{idx}",
                        "page": b.page_number,
                        "text": entry_text,
                        "label": label,
                        "section_id": b.section_id,
                        "section_title": b.section_title,
                        "section_path": b.section_path,
                    }
                )

        if not references and full_text:
            for idx, entry in enumerate(DBIngestionPipeline._extract_references_from_full_text(full_text)):
                references.append(
                    {
                        "id": f"fulltext_ref_{idx}",
                        "page": None,
                        "text": entry,
                        "label": "reference",
                        "section_id": None,
                        "section_title": "References",
                        "section_path": None,
                    }
                )

        return {
            "text_blocks": text_blocks,
            "tables": tables,
            "figures": figures,
            "references": references,
        }

    @staticmethod
    def _split_reference_entries(text: str) -> list[str]:
        """Split a reference block into individual entries when patterns are clear."""
        para_chunks = [chunk.strip() for chunk in re.split(r"\r?\n\s*\r?\n+", text) if chunk.strip()]
        if para_chunks:
            first = re.sub(r"^\s*(references|bibliography|works cited)\s*:?\s*", "", para_chunks[0], flags=re.I)
            para_chunks[0] = first.strip()
            para_chunks = [c for c in para_chunks if c]
            if len(para_chunks) > 1:
                return para_chunks

        lines = [ln.strip() for ln in re.split(r"\r?\n+", text) if ln.strip()]
        if len(lines) > 1:
            marker = re.compile(r"^(\[\d+\]|\(\d+\)|\d+\.|\d+\)|[-•])\s+")
            if any(marker.match(ln) for ln in lines):
                merged: list[str] = []
                for ln in lines:
                    if marker.match(ln):
                        merged.append(ln)
                    elif merged:
                        merged[-1] = f"{merged[-1]} {ln}".strip()
                    else:
                        merged.append(ln)
                return merged

            if all(len(ln) > 30 for ln in lines):
                return lines

        inline = re.split(r"(?=(?:\[\d+\]|\(\d+\)|\d+\.\s))", text)
        inline = [part.strip() for part in inline if part and part.strip()]
        if len(inline) > 1:
            return inline

        return []

    @staticmethod
    def _looks_like_reference_block(text: str) -> bool:
        value = (text or "").strip()
        if not value:
            return False

        heading_match = re.match(r"^\s*(references|bibliography|works cited)\b", value, flags=re.I)
        if heading_match:
            return True

        # Catch common citation signatures even when section metadata is missing.
        if re.search(r"\barXiv\b|\bdoi\b|\bProceedings\b|\bet al\.\b", value, flags=re.I):
            year_hits = len(re.findall(r"\b(19|20)\d{2}\b", value))
            if year_hits >= 2 and len(value) > 200:
                return True

        return False

    @staticmethod
    def _extract_references_from_full_text(full_text: str) -> list[str]:
        """Extract reference entries from full text when block-level metadata misses them."""
        text = (full_text or "").strip()
        if not text:
            return []

        match = re.search(r"\b(references|bibliography|works cited)\b", text, flags=re.I)
        if not match:
            return []

        tail = text[match.end():].strip()
        if not tail:
            return []

        entries = DBIngestionPipeline._split_reference_entries(tail)
        if entries:
            return entries

        # Fallback: keep non-trivial lines as entries.
        lines = [ln.strip() for ln in re.split(r"\r?\n+", tail) if ln.strip()]
        return [ln for ln in lines if len(ln) > 20]
