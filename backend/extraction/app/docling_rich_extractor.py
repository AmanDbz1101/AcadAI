"""
Docling-enhanced rich extractor.

Runs a single Docling conversion pass and produces ALL structured data
needed to populate the PostgreSQL database:
  - Full section hierarchy with bounding boxes
  - Every text block with page, bbox, label, section assignment, font info
  - Tables with serialised cell data
  - Figures with caption and bbox
  - Formulas/equations

This module DOES NOT replace the existing extraction pipeline.
It is an *enhancement* layer that produces richer data alongside the
existing pipeline's output (metadata JSON, hierarchy JSON, etc.).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument
from backend.extraction.app.pdf_loader import _get_accelerator_options

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data-transfer objects (plain dataclasses – no ORM dependency here)
# ---------------------------------------------------------------------------

@dataclass
class BBoxData:
    l: float
    t: float
    r: float
    b: float
    coord_origin: str = "BOTTOMLEFT"


@dataclass
class RichSectionData:
    section_id: str
    title: str
    level: int
    numbering: Optional[str]
    parent_id: Optional[str]
    page_start: int
    page_end: Optional[int]
    reading_order: int
    font_size: Optional[float]
    is_bold: Optional[bool]
    bbox: Optional[BBoxData]


@dataclass
class RichTextBlock:
    block_id: str
    content: str
    label: str
    page_number: int
    reading_order: int
    section_id: Optional[str]
    section_title: Optional[str]
    section_level: Optional[int]
    section_path: Optional[str]
    bbox: Optional[BBoxData]
    font_name: Optional[str]
    font_size: Optional[float]
    is_bold: Optional[bool]
    is_italic: Optional[bool]


@dataclass
class RichTableData:
    table_id: str
    caption: Optional[str]
    page_number: int
    reading_order: int
    section_id: Optional[str]
    section_title: Optional[str]
    bbox: Optional[BBoxData]
    row_count: Optional[int]
    col_count: Optional[int]
    table_data: Optional[dict]   # {"rows": [[cell, …], …], "headers": [col, …]}


@dataclass
class RichFigureData:
    figure_id: str
    caption: Optional[str]
    page_number: int
    reading_order: int
    section_id: Optional[str]
    section_title: Optional[str]
    bbox: Optional[BBoxData]


@dataclass
class RichFormulaData:
    formula_id: str
    content: Optional[str]
    page_number: int
    reading_order: int
    section_id: Optional[str]
    section_title: Optional[str]
    bbox: Optional[BBoxData]


@dataclass
class DoclingRichResult:
    """All structured data extracted from a single PDF."""
    pdf_path: str
    pdf_hash: str
    filename: str
    total_pages: int
    sections: list[RichSectionData] = field(default_factory=list)
    text_blocks: list[RichTextBlock] = field(default_factory=list)
    tables: list[RichTableData] = field(default_factory=list)
    figures: list[RichFigureData] = field(default_factory=list)
    formulas: list[RichFormulaData] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

_TEXT_LABELS = {
    "text", "paragraph", "list_item", "section_header", "title",
    "caption", "footnote", "page_header", "page_footer", "reference",
    "code", "formula",  # formula as text when no enrichment
}

_FORMULA_LABELS = {"formula", "equation"}
_HEADER_LABELS = {"section_header", "title"}


class DoclingRichExtractor:
    """
    Runs Docling with table-structure + picture extraction enabled and
    returns a :class:`DoclingRichResult` with rich per-element data.

    One instance can be reused across multiple documents (the Docling
    converter is expensive to initialise).
    """

    def __init__(
        self,
        extract_tables: bool = True,
        extract_pictures: bool = True,
        images_scale: float = 1.0,
        num_threads: int = 4,
    ):
        pipeline_options = PdfPipelineOptions(
            do_table_structure=extract_tables,
            generate_picture_images=extract_pictures,
            images_scale=images_scale,
            accelerator_options=_get_accelerator_options(num_threads),
        )
        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        )
        logger.info("DoclingRichExtractor initialised (tables=%s, pictures=%s)",
                    extract_tables, extract_pictures)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, pdf_path: Path) -> DoclingRichResult:
        """
        Extract rich structured data from a PDF.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            :class:`DoclingRichResult` with all element data.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        pdf_hash = self._hash_file(pdf_path)
        logger.info("DoclingRichExtractor: converting %s …", pdf_path.name)

        result = self._converter.convert(str(pdf_path))
        doc: DoclingDocument = result.document

        total_pages = doc.num_pages()

        # --- Build section hierarchy first so we can assign sections to blocks ---
        sections, section_map = self._extract_sections(doc)

        # --- Text blocks ---
        text_blocks, reading_order_counter = self._extract_text_blocks(
            doc, section_map
        )

        # --- Tables ---
        tables = self._extract_tables(doc, section_map, reading_order_counter)
        reading_order_counter += len(tables)

        # --- Figures ---
        figures = self._extract_figures(doc, section_map, reading_order_counter)
        reading_order_counter += len(figures)

        # --- Formulas (captured separately from text blocks) ---
        formulas = self._extract_formulas(doc, section_map, reading_order_counter)

        return DoclingRichResult(
            pdf_path=str(pdf_path),
            pdf_hash=pdf_hash,
            filename=pdf_path.name,
            total_pages=total_pages,
            sections=sections,
            text_blocks=text_blocks,
            tables=tables,
            figures=figures,
            formulas=formulas,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _make_id(item: Any) -> str:
        """Stable ID derived from item repr (same as in metadata_extractor)."""
        return hashlib.md5(str(item).encode()).hexdigest()

    @staticmethod
    def _get_page_no(item: Any) -> int:
        """Return 1-indexed page number from a Docling item."""
        if hasattr(item, "prov") and item.prov:
            return getattr(item.prov[0], "page_no", 0) + 1  # docling is 0-indexed
        return 1

    @staticmethod
    def _get_bbox(item: Any) -> Optional[BBoxData]:
        if hasattr(item, "prov") and item.prov:
            bbox = getattr(item.prov[0], "bbox", None)
            if bbox is not None:
                coord_origin = getattr(bbox, "coord_origin", None)
                origin_str = str(coord_origin).split(".")[-1] if coord_origin else "BOTTOMLEFT"
                return BBoxData(
                    l=float(getattr(bbox, "l", 0)),
                    t=float(getattr(bbox, "t", 0)),
                    r=float(getattr(bbox, "r", 0)),
                    b=float(getattr(bbox, "b", 0)),
                    coord_origin=origin_str,
                )
        return None

    @staticmethod
    def _get_text(item: Any) -> str:
        return getattr(item, "text", None) or ""

    # ------------------------------------------------------------------
    # Section extraction
    # ------------------------------------------------------------------

    def _extract_sections(
        self, doc: DoclingDocument
    ) -> tuple[list[RichSectionData], dict[int, dict]]:
        """
        Extract section hierarchy.

        Returns
        -------
        sections:
            List of :class:`RichSectionData` in reading order.
        section_map:
            Dict mapping reading_order → {section_id, title, level, path} for
            assigning sections to subsequent element blocks.
        """
        sections: list[RichSectionData] = []
        # Stack of (level, section_id, title) for parent resolution
        level_stack: list[tuple[int, str, str]] = []
        section_map: dict[int, dict] = {}   # reading_order → section context

        reading_order = 0
        for item, level_hint in doc.iterate_items():
            label = str(getattr(item, "label", "")).lower()
            if label not in ("section_header", "title"):
                reading_order += 1
                continue

            text = self._get_text(item)
            if not text.strip():
                reading_order += 1
                continue

            section_id = self._make_id(item)
            page_no = self._get_page_no(item)
            bbox = self._get_bbox(item)

            # Determine level from heading depth hint
            section_level = level_hint if isinstance(level_hint, int) else 1

            # Resolve parent
            parent_id: Optional[str] = None
            while level_stack and level_stack[-1][0] >= section_level:
                level_stack.pop()
            if level_stack:
                parent_id = level_stack[-1][1]

            # Build path string e.g. "Introduction > 1.1 Background"
            parent_path = level_stack[-1][2] if level_stack else None
            path = f"{parent_path} > {text}" if parent_path else text

            level_stack.append((section_level, section_id, path))

            rich = RichSectionData(
                section_id=section_id,
                title=text,
                level=section_level,
                numbering=None,
                parent_id=parent_id,
                page_start=page_no,
                page_end=None,
                reading_order=reading_order,
                font_size=None,
                is_bold=None,
                bbox=bbox,
            )
            sections.append(rich)

            # Map this reading_order position → section context
            section_map[reading_order] = {
                "section_id": section_id,
                "title": text,
                "level": section_level,
                "path": path,
            }

            reading_order += 1

        # Back-fill page_end for each section
        for i, sec in enumerate(sections):
            if i + 1 < len(sections):
                sec.page_end = sections[i + 1].page_start
            # else: page_end remains None (last section spans to end)

        return sections, section_map

    # ------------------------------------------------------------------
    # Text blocks
    # ------------------------------------------------------------------

    def _extract_text_blocks(
        self, doc: DoclingDocument, section_map: dict[int, dict]
    ) -> tuple[list[RichTextBlock], int]:
        """Extract all text-level elements."""
        blocks: list[RichTextBlock] = []
        current_section: Optional[dict] = None
        reading_order = 0

        for item, _level in doc.iterate_items():
            label = str(getattr(item, "label", "")).lower()

            # Update current section when we hit a header
            if label in ("section_header", "title"):
                if reading_order in section_map:
                    current_section = section_map[reading_order]
                reading_order += 1
                continue

            # Skip non-text elements (tables / pictures handled separately)
            if label not in _TEXT_LABELS or label in _FORMULA_LABELS:
                reading_order += 1
                continue

            text = self._get_text(item)
            if not text.strip():
                reading_order += 1
                continue

            bbox = self._get_bbox(item)
            page_no = self._get_page_no(item)
            block_id = self._make_id(item)

            block = RichTextBlock(
                block_id=block_id,
                content=text,
                label=label,
                page_number=page_no,
                reading_order=reading_order,
                section_id=current_section["section_id"] if current_section else None,
                section_title=current_section["title"] if current_section else None,
                section_level=current_section["level"] if current_section else None,
                section_path=current_section["path"] if current_section else None,
                bbox=bbox,
                font_name=None,   # Docling doesn't expose font_name via public API
                font_size=None,
                is_bold=None,
                is_italic=None,
            )
            blocks.append(block)
            reading_order += 1

        return blocks, reading_order

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def _extract_tables(
        self, doc: DoclingDocument, section_map: dict[int, dict], start_order: int
    ) -> list[RichTableData]:
        tables: list[RichTableData] = []

        # Build a quick lookup: page_no → last section before that page
        section_for_page = self._build_section_page_lookup(doc, section_map)

        for i, table in enumerate(doc.tables):
            page_no = table.prov[0].page_no + 1 if table.prov else 1
            bbox = self._get_bbox(table)
            caption = getattr(table, "caption_text", lambda _: None)(doc) or None
            sec_ctx = self._get_section_for_element(page_no, section_for_page)

            # Serialise table to row/column data
            table_data = None
            row_count = col_count = None
            try:
                df = table.export_to_dataframe(doc)
                row_count = len(df)
                col_count = len(df.columns)
                table_data = {
                    "headers": list(df.columns.astype(str)),
                    "rows": df.astype(str).values.tolist(),
                }
            except Exception:
                try:
                    # Older Docling API fallback
                    df = table.export_to_dataframe()
                    row_count = len(df)
                    col_count = len(df.columns)
                    table_data = {
                        "headers": list(df.columns.astype(str)),
                        "rows": df.astype(str).values.tolist(),
                    }
                except Exception:
                    pass

            tables.append(
                RichTableData(
                    table_id=self._make_id(table),
                    caption=caption,
                    page_number=page_no,
                    reading_order=start_order + i,
                    section_id=sec_ctx.get("section_id") if sec_ctx else None,
                    section_title=sec_ctx.get("title") if sec_ctx else None,
                    bbox=bbox,
                    row_count=row_count,
                    col_count=col_count,
                    table_data=table_data,
                )
            )
        return tables

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    def _extract_figures(
        self, doc: DoclingDocument, section_map: dict[int, dict], start_order: int
    ) -> list[RichFigureData]:
        figures: list[RichFigureData] = []
        section_for_page = self._build_section_page_lookup(doc, section_map)

        for i, pic in enumerate(doc.pictures):
            page_no = pic.prov[0].page_no + 1 if pic.prov else 1
            bbox = self._get_bbox(pic)
            caption = getattr(pic, "caption_text", lambda _: None)(doc) or None
            sec_ctx = self._get_section_for_element(page_no, section_for_page)

            figures.append(
                RichFigureData(
                    figure_id=self._make_id(pic),
                    caption=caption,
                    page_number=page_no,
                    reading_order=start_order + i,
                    section_id=sec_ctx.get("section_id") if sec_ctx else None,
                    section_title=sec_ctx.get("title") if sec_ctx else None,
                    bbox=bbox,
                )
            )
        return figures

    # ------------------------------------------------------------------
    # Formulas
    # ------------------------------------------------------------------

    def _extract_formulas(
        self, doc: DoclingDocument, section_map: dict[int, dict], start_order: int
    ) -> list[RichFormulaData]:
        formulas: list[RichFormulaData] = []
        section_for_page = self._build_section_page_lookup(doc, section_map)
        current_section: Optional[dict] = None
        reading_order = 0

        for item, _level in doc.iterate_items():
            label = str(getattr(item, "label", "")).lower()

            if label in ("section_header", "title"):
                if reading_order in section_map:
                    current_section = section_map[reading_order]
                reading_order += 1
                continue

            if label not in _FORMULA_LABELS:
                reading_order += 1
                continue

            page_no = self._get_page_no(item)
            bbox = self._get_bbox(item)
            text = self._get_text(item)

            sec_ctx = current_section or self._get_section_for_element(
                page_no, section_for_page
            )

            formulas.append(
                RichFormulaData(
                    formula_id=self._make_id(item),
                    content=text or None,
                    page_number=page_no,
                    reading_order=start_order + len(formulas),
                    section_id=sec_ctx.get("section_id") if sec_ctx else None,
                    section_title=sec_ctx.get("title") if sec_ctx else None,
                    bbox=bbox,
                )
            )
            reading_order += 1

        return formulas

    # ------------------------------------------------------------------
    # Section ↔ page helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_section_page_lookup(
        doc: DoclingDocument, section_map: dict[int, dict]
    ) -> dict[int, dict]:
        """
        Build a mapping page_no → last known section context.
        Used for elements (tables, figures) that are not in the text stream.
        """
        # Collect (page_no, section) in order and build a lookup
        page_section: dict[int, dict] = {}
        for order, ctx in sorted(section_map.items()):
            page = 1
            for item, _level in doc.iterate_items():
                label = str(getattr(item, "label", "")).lower()
                if label in ("section_header", "title") and DoclingRichExtractor._make_id(item) == ctx.get("section_id"):
                    page = DoclingRichExtractor._get_page_no(item)
                    break
            page_section[page] = ctx
        return page_section

    @staticmethod
    def _get_section_for_element(
        page_no: int, page_section: dict[int, dict]
    ) -> Optional[dict]:
        """Return the latest section that starts on or before `page_no`."""
        best: Optional[dict] = None
        for p, ctx in sorted(page_section.items()):
            if p <= page_no:
                best = ctx
            else:
                break
        return best
