"""
Section-aware chunker.

Assigns document text to the corresponding section node from the hierarchy,
then applies token-aware sliding-window splitting within each section so that
every chunk carries full section context (breadcrumb path, level, IDs).

Text sourcing strategy
-----------------------
1. **PDF path provided** ─ PyMuPDF extracts page-level text; pages are assigned
   to section nodes using ``page_start``/``page_end`` ranges.
2. **PDF not available** ─ falls back to ``_fulltext.txt``; section boundaries
   are detected by matching section titles in the raw text.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Optional

from rag.retrieval.chunking.models import Chunk
from rag.retrieval.chunking.text_splitter import TokenAwareSplitter
from rag.retrieval.config import (
    FINE_CHUNK_SIZE,
    FINE_CHUNK_OVERLAP,
    COARSE_CHUNK_SIZE,
    COARSE_CHUNK_OVERLAP,
    DENSE_MODEL,
    CHUNK_MIN_CHARS,
)

ElementDict = dict[str, list[dict]]

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_hierarchy(hierarchy_path: Path) -> dict:
    with open(hierarchy_path, encoding="utf-8") as f:
        raw = json.load(f)
    return raw.get("hierarchy", raw)


def _load_complete(complete_path: Path) -> dict:
    with open(complete_path, encoding="utf-8") as f:
        return json.load(f)


def _build_section_path(
    section_id: str,
    sections_by_id: dict[str, dict],
) -> list[str]:
    """Return ancestor chain as title list from root down to this node."""
    path: list[str] = []
    current_id: Optional[str] = section_id
    while current_id:
        node = sections_by_id.get(current_id)
        if not node:
            break
        path.insert(0, node.get("title", ""))
        current_id = node.get("parent_id")
    return path


def _extract_pages_pymupdf(pdf_path: Path) -> dict[int, str]:
    """Return {page_number (1-based): page_text} for the whole PDF."""
    try:
        import fitz  # type: ignore  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        pages: dict[int, str] = {}
        for i, page in enumerate(doc, start=1):
            pages[i] = page.get_text("text")
        doc.close()
        return pages
    except ImportError:
        logger.warning("PyMuPDF not available; will fall back to fulltext.txt")
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("PyMuPDF extraction failed (%s); will fall back to fulltext.txt", exc)
        return {}


def _text_for_section_pages(
    page_texts: dict[int, str],
    page_start: Optional[int],
    page_end: Optional[int],
) -> str:
    """Concatenate text from pages in [page_start, page_end]."""
    if not page_texts or page_start is None:
        return ""
    end = page_end or page_start
    return "\n\n".join(
        page_texts[p] for p in range(page_start, end + 1) if p in page_texts
    )


def _segment_fulltext_by_sections(
    full_text: str,
    sections: list[dict],
) -> dict[str, str]:
    """
    Heuristic fulltext segmentation using title matching.

    Returns {section_id: section_text}.

    Each section's text runs from its title header to the next section's
    title header.  Sections whose titles cannot be found in the text receive
    the empty string.
    """
    if not full_text or not sections:
        return {}

    # Build (offset, section_id) pairs sorted by occurrence position.
    anchors: list[tuple[int, str]] = []
    for node in sections:
        title = node.get("title", "").strip()
        section_id = node["section_id"]
        if not title:
            continue
        # Try numbered header (e.g. "1 Introduction" or "3.2 Attention")
        numbering = node.get("numbering") or ""
        patterns = [title]
        if numbering:
            patterns.insert(0, rf"{re.escape(numbering)}\s+{re.escape(title)}")

        pos = -1
        for pat in patterns:
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                pos = m.start()
                break
        if pos >= 0:
            anchors.append((pos, section_id))

    if not anchors:
        return {}

    anchors.sort()
    seg: dict[str, str] = {}
    for idx, (start, sec_id) in enumerate(anchors):
        end = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(full_text)
        seg[sec_id] = full_text[start:end].strip()
    return seg


def summarize_table(markdown_content: str) -> str:
    """Summarize markdown table content using Groq for better embedding quality."""
    if not markdown_content.strip():
        return markdown_content

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        logger.warning("GROQ_API_KEY not found; using raw table markdown as chunk content")
        return markdown_content

    prompt = (
        "You are processing a research paper. Convert the following table into a clear natural language "
        "summary that captures all key data, relationships, and findings present in the table. "
        "Do not add any information not present in the table. Return only the summary, no preamble."
    )

    try:
        from groq import Groq

        client = Groq(api_key=groq_api_key)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "user",
                    "content": f"{prompt}\n\n{markdown_content}",
                }
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        summary = (response.choices[0].message.content or "").strip()
        return summary if summary else markdown_content
    except Exception as exc:  # noqa: BLE001
        logger.warning("Table summarization failed (%s); using raw table markdown", exc)
        return markdown_content


def summarize_figure(caption: str, image_path: str) -> str:
    """Summarize a figure using the image file and caption via Groq multimodal API."""
    caption = caption.strip()

    if not image_path:
        return caption

    if not os.path.exists(image_path):
        logger.warning(
            "Figure image file not found at %s; using caption text for figure chunk",
            image_path,
        )
        return caption

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        logger.warning("GROQ_API_KEY not found; using caption text for figure chunk")
        return caption

    media_type, _ = mimetypes.guess_type(image_path)
    if media_type and media_type.startswith("image/"):
        ext = media_type.split("/", 1)[1].lower()
    else:
        ext = Path(image_path).suffix.lower().lstrip(".")

    ext = {
        "jpg": "jpeg",
        "jpeg": "jpeg",
        "png": "png",
        "gif": "gif",
        "webp": "webp",
        "bmp": "bmp",
        "tif": "tiff",
        "tiff": "tiff",
    }.get(ext, "png")

    prompt = (
        f"You are processing a research paper figure. The caption is: '{caption}'. "
        "Based on the image and caption, write a clear natural language description of what this figure "
        "shows, what it represents, and why it is significant in the context of the paper. "
        "Return only the description, no preamble."
    )

    try:
        with open(image_path, "rb") as image_file:
            b64_string = base64.b64encode(image_file.read()).decode("utf-8")

        from groq import Groq

        client = Groq(api_key=groq_api_key)
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{ext};base64,{b64_string}",
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        summary = (response.choices[0].message.content or "").strip()
        return summary if summary else caption
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Figure summarization failed for %s (%s); using caption text",
            image_path,
            exc,
        )
        return caption


# ── Public class ─────────────────────────────────────────────────────────────

class SectionChunker:
    """
    Convert a processed document (hierarchy.json + complete.json / fulltext.txt)
    into a flat list of :class:`Chunk` objects ready for embedding.

    Parameters
    ----------
    fine_chunk_size : int
        Maximum tokens per fine-grained chunk.
    fine_chunk_overlap : int
        Overlap tokens between consecutive fine chunks.
    coarse_chunk_size : int
        Maximum tokens per coarse-grained chunk.
    coarse_chunk_overlap : int
        Overlap tokens between consecutive coarse chunks.
    model_name : str
        HuggingFace model name used by the internal ``TokenAwareSplitter``
        for accurate token counting.
    """

    def __init__(
        self,
        fine_chunk_size: int = FINE_CHUNK_SIZE,
        fine_chunk_overlap: int = FINE_CHUNK_OVERLAP,
        coarse_chunk_size: int = COARSE_CHUNK_SIZE,
        coarse_chunk_overlap: int = COARSE_CHUNK_OVERLAP,
        model_name: str = DENSE_MODEL,
    ) -> None:
        self.fine_splitter = TokenAwareSplitter(
            chunk_size=fine_chunk_size,
            chunk_overlap=fine_chunk_overlap,
            model_name=model_name,
        )
        self.coarse_splitter = TokenAwareSplitter(
            chunk_size=coarse_chunk_size,
            chunk_overlap=coarse_chunk_overlap,
            model_name=model_name,
        )

    # ── Main entry point ──────────────────────────────────────────────────────

    def chunk_document(
        self,
        hierarchy_json_path: Path,
        output_dir: Optional[Path] = None,
        pdf_path: Optional[Path] = None,
    ) -> list[Chunk]:
        """
        Produce chunks for a document.

        Parameters
        ----------
        hierarchy_json_path : Path
            Path to the ``<document_id>_hierarchy.json`` output file.
        output_dir : Path, optional
            Directory where ``_complete.json`` and ``_fulltext.txt`` live.
            Inferred from *hierarchy_json_path*'s parent when omitted.
        pdf_path : Path, optional
            Original PDF.  When provided, PyMuPDF is used for per-page text;
            otherwise fulltext.txt is used.

        Returns
        -------
        list[Chunk]
            Ordered list of chunks, section-annotated and token-aware.
        """
        hierarchy_json_path = Path(hierarchy_json_path)
        output_dir = output_dir or hierarchy_json_path.parent

        # ── Load hierarchy ────────────────────────────────────────────────────
        hier = _load_hierarchy(hierarchy_json_path)
        document_id: str = hier.get("document_id", "")
        all_section_nodes: list[dict] = hier.get("sections", [])

        if not all_section_nodes:
            logger.warning("No section nodes found in %s", hierarchy_json_path)
            return self._fallback_full_text_chunks(document_id, output_dir)

        # Index by section_id for O(1) lookup
        sections_by_id: dict[str, dict] = {
            s["section_id"]: s for s in all_section_nodes
        }

        # ── Gather page-level text ────────────────────────────────────────────
        page_texts: dict[int, str] = {}
        if pdf_path and Path(pdf_path).exists():
            page_texts = _extract_pages_pymupdf(Path(pdf_path))

        # ── Build section → text mapping ─────────────────────────────────────
        section_texts: dict[str, str] = {}

        if page_texts:
            # Prefer page-based assignment
            for node in all_section_nodes:
                section_texts[node["section_id"]] = _text_for_section_pages(
                    page_texts,
                    node.get("page_start"),
                    node.get("page_end"),
                )
        else:
            # Fallback: segment fulltext by section headers
            fulltext_path = output_dir / f"{document_id}_fulltext.txt"
            if fulltext_path.exists():
                full_text = fulltext_path.read_text(encoding="utf-8")
                section_texts = _segment_fulltext_by_sections(
                    full_text, all_section_nodes
                )
            else:
                logger.warning(
                    "Neither PDF nor fulltext found for %s; returning empty chunk list",
                    document_id,
                )
                return []

        # ── Load extracted elements from complete.json ────────────────────────
        extracted_elements = self._load_extracted_elements(document_id, output_dir)

        # ── Produce chunks ────────────────────────────────────────────────────
        chunks: list[Chunk] = []
        chunk_index = 0

        # Process in reading_order for deterministic output
        ordered_nodes = sorted(all_section_nodes, key=lambda n: n.get("reading_order", 0))

        for node in ordered_nodes:
            section_id = node["section_id"]
            text = section_texts.get(section_id, "").strip()

            if not text or len(text) < CHUNK_MIN_CHARS:
                continue  # skip empty / near-empty sections

            section_path = _build_section_path(section_id, sections_by_id)

            # Gather element_ids from complete.json if available (best-effort)
            element_ids = self._collect_element_ids(
                document_id, output_dir, node
            )

            # ── Extract tables and figures for this section ──────────────────
            tables, figures = self._extract_elements_for_section(
                extracted_elements,
                node.get("page_start"),
                node.get("page_end"),
            )

            # Create chunks for tables
            for table in tables:
                chunk, chunk_index = self._create_table_chunk(
                    table,
                    document_id,
                    chunk_index,
                    section_id,
                    node.get("title", ""),
                    node.get("level", 1),
                    node.get("numbering"),
                    section_path,
                    node.get("parent_id"),
                    node.get("page_start"),
                    node.get("page_end"),
                    str(pdf_path.name if pdf_path else f"{document_id}_fulltext.txt"),
                )
                chunks.append(chunk)

            # Create chunks for figures
            for figure in figures:
                figure_chunk = self._create_figure_chunk(
                    figure,
                    document_id,
                    chunk_index,
                    section_id,
                    node.get("title", ""),
                    node.get("level", 1),
                    node.get("numbering"),
                    section_path,
                    node.get("parent_id"),
                    node.get("page_start"),
                    node.get("page_end"),
                    str(pdf_path.name if pdf_path else f"{document_id}_fulltext.txt"),
                )
                if figure_chunk is None:
                    continue
                chunk, chunk_index = figure_chunk
                chunks.append(chunk)

            # Split the remaining section text into regular text chunks
            for chunk_level, splitter in (
                ("fine", self.fine_splitter),
                ("coarse", self.coarse_splitter),
            ):
                windows = splitter.split(text)
                for window in windows:
                    if len(window) < CHUNK_MIN_CHARS:
                        continue

                    chunks.append(
                        Chunk(
                            document_id=document_id,
                            content=window,
                            content_type="text",
                            token_count=splitter.count_tokens(window),
                            chunk_index=chunk_index,
                            chunk_level=chunk_level,
                            section_id=section_id,
                            section_title=node.get("title", ""),
                            section_level=node.get("level", 1),
                            section_numbering=node.get("numbering"),
                            section_path=section_path,
                            parent_section_id=node.get("parent_id"),
                            page_start=node.get("page_start"),
                            page_end=node.get("page_end"),
                            element_ids=element_ids,
                            source_file=str(
                                pdf_path.name if pdf_path else f"{document_id}_fulltext.txt"
                            ),
                        )
                    )
                    chunk_index += 1

        logger.info(
            "SectionChunker: %d chunks from %d sections for document %s",
            len(chunks),
            len(ordered_nodes),
            document_id,
        )
        return chunks

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _load_extracted_elements(
        document_id: str,
        output_dir: Path,
    ) -> Optional[ElementDict]:
        """
        Load extracted_elements dict from _complete.json.
        Returns None if file is not available.
        """
        try:
            complete_path = output_dir / f"{document_id}_complete.json"
            if not complete_path.exists():
                return None
            with open(complete_path, encoding="utf-8") as f:
                complete = json.load(f)
            return complete.get("extracted_elements", {})
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _extract_elements_for_section(
        elements: Optional[ElementDict],
        page_start: Optional[int],
        page_end: Optional[int],
    ) -> tuple[list[dict], list[dict]]:
        """
        Extract tables and figures that fall within the section's page range.
        
        Returns (tables, figures) lists of elements within [page_start, page_end].
        """
        tables: list[dict] = []
        figures: list[dict] = []

        if not elements or page_start is None:
            return tables, figures

        page_range_end = page_end or page_start

        # Extract tables
        for table in elements.get("tables", []):
            page = table.get("page")
            if page is not None and page_start <= page <= page_range_end:
                tables.append(table)

        # Extract figures
        for figure in elements.get("figures", []):
            page = figure.get("page")
            if page is not None and page_start <= page <= page_range_end:
                figures.append(figure)

        return tables, figures

    @staticmethod
    def _create_table_chunk(
        table: dict,
        document_id: str,
        chunk_index: int,
        section_id: Optional[str],
        section_title: str,
        section_level: int,
        section_numbering: Optional[str],
        section_path: list[str],
        parent_section_id: Optional[str],
        page_start: Optional[int],
        page_end: Optional[int],
        source_file: str,
    ) -> tuple[Chunk, int]:
        """Create a single chunk for a table. Returns (chunk, new_chunk_index)."""
        # Use markdown if available, otherwise fall back to text.
        original_content = table.get("markdown") or table.get("text", "")
        content = summarize_table(original_content)
        
        chunk = Chunk(
            document_id=document_id,
            content=content,
            original_content=original_content,
            content_type="table",
            token_count=0,  # Tables are not split, but could be counted
            chunk_index=chunk_index,
            chunk_level="coarse",  # Tables are treated as coarse chunks
            section_id=section_id,
            section_title=section_title,
            section_level=section_level,
            section_numbering=section_numbering,
            section_path=section_path,
            parent_section_id=parent_section_id,
            page_start=page_start,
            page_end=page_end,
            element_ids=[table.get("id", "")],
            source_file=source_file,
        )
        return chunk, chunk_index + 1

    @staticmethod
    def _create_figure_chunk(
        figure: dict,
        document_id: str,
        chunk_index: int,
        section_id: Optional[str],
        section_title: str,
        section_level: int,
        section_numbering: Optional[str],
        section_path: list[str],
        parent_section_id: Optional[str],
        page_start: Optional[int],
        page_end: Optional[int],
        source_file: str,
    ) -> Optional[tuple[Chunk, int]]:
        """Create a single chunk for a figure. Returns None when cleaned content is empty."""
        # Combine caption and image path reference
        caption = figure.get("caption", "").strip()
        figure_image_path = figure.get("image_path", "")

        if figure_image_path:
            content = f"{caption}\n[Image: {figure_image_path}]" if caption else f"[Image: {figure_image_path}]"
        else:
            content = caption or "[Figure without caption]"

        # Extract image path from the inline reference before stripping it.
        image_path_match = re.search(r"\[Image:\s*(.*?)\]", content)
        image_path = image_path_match.group(1).strip() if image_path_match else ""

        # Remove inline base64 image payloads and image-path references to get caption text.
        caption_text = re.sub(
            r"!\[.*?\]\(data:image\/[^;]+;base64,[^\)]+\)",
            "",
            content,
        )
        caption_text = re.sub(r"\[Image:.*?\]", "", caption_text)
        caption_text = caption_text.strip()

        if not image_path and figure_image_path:
            image_path = figure_image_path

        if image_path:
            content = summarize_figure(caption_text, image_path)
        else:
            content = caption_text

        if not content:
            return None

        chunk = Chunk(
            document_id=document_id,
            content=content,
            original_content=caption_text,
            content_type="figure",
            image_path=image_path or None,
            token_count=0,  # Figures are not split, but could be counted
            chunk_index=chunk_index,
            chunk_level="coarse",  # Figures are treated as coarse chunks
            section_id=section_id,
            section_title=section_title,
            section_level=section_level,
            section_numbering=section_numbering,
            section_path=section_path,
            parent_section_id=parent_section_id,
            page_start=page_start,
            page_end=page_end,
            element_ids=[figure.get("id", "")],
            source_file=source_file,
        )
        return chunk, chunk_index + 1

    @staticmethod
    def _collect_element_ids(
        document_id: str,
        output_dir: Path,
        section_node: dict,
    ) -> list[str]:
        """
        Try to pull element_ids from the _complete.json ``sections[].stats``.
        Returns an empty list if information is unavailable.
        """
        try:
            complete_path = output_dir / f"{document_id}_complete.json"
            if not complete_path.exists():
                return []
            with open(complete_path, encoding="utf-8") as f:
                complete = json.load(f)

            # Flat walk of sections list looking for title match
            needle = section_node.get("title", "").strip().lower()
            metadata = complete.get("metadata", {})
            all_secs = _flatten_sections(metadata.get("sections", []))
            for sec in all_secs:
                if sec.get("original_name", "").strip().lower() == needle:
                    stats = sec.get("stats", {})
                    ids: list[str] = []
                    for key in ("formula_ids", "table_ids", "figure_ids", "text_block_ids"):
                        ids.extend(stats.get(key, []))
                    return ids
        except Exception:  # noqa: BLE001
            pass
        return []

    def _fallback_full_text_chunks(
        self, document_id: str, output_dir: Path
    ) -> list[Chunk]:
        """
        Last-resort: chunk the entire fulltext.txt without section context.
        Used when hierarchy is empty or missing.
        """
        fulltext_path = output_dir / f"{document_id}_fulltext.txt"
        if not fulltext_path.exists():
            return []

        full_text = fulltext_path.read_text(encoding="utf-8").strip()
        if not full_text:
            return []

        windows = self.coarse_splitter.split(full_text)
        return [
            Chunk(
                document_id=document_id,
                content=w,
                content_type="text",
                token_count=self.coarse_splitter.count_tokens(w),
                chunk_index=i,
                chunk_level="coarse",
                section_title="",
                section_level=1,
                section_path=[],
                source_file=f"{document_id}_fulltext.txt",
            )
            for i, w in enumerate(windows)
            if len(w) >= CHUNK_MIN_CHARS
        ]


def _flatten_sections(sections: list[dict]) -> list[dict]:
    """Recursively flatten nested sections list."""
    result = []
    for s in sections:
        result.append(s)
        result.extend(_flatten_sections(s.get("sections", [])))
    return result
