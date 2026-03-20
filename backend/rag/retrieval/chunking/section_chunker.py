"""
Section-aware chunker.

Assigns document text to the corresponding section node from the hierarchy,
then applies token-aware sliding-window splitting within each section so that
every chunk carries full section context (breadcrumb path, level, IDs).

Text sourcing strategy
-----------------------
1. **PDF path provided** ─ PyMuPDF extracts page-level text; pages are assigned
   to section nodes using ``page_start``/``page_end`` ranges.
2. **PDF not available** ─ falls back to ``_fulltext.txt``.
3. **No fulltext sidecar** ─ reconstructs text from ``_complete.json``
    ``extracted_elements.text_blocks``.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import uuid
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

_REFERENCE_SECTION_KEYWORDS = (
    "reference",
    "references",
    "bibliography",
    "works cited",
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_hierarchy(hierarchy_path: Path) -> dict:
    with open(hierarchy_path, encoding="utf-8") as f:
        raw = json.load(f)
    return raw.get("hierarchy", raw)


def _load_complete(complete_path: Path) -> dict:
    with open(complete_path, encoding="utf-8") as f:
        return json.load(f)


def _full_text_from_complete(complete_doc: dict) -> str:
    """Reconstruct best-effort full text from complete.json text blocks."""
    extracted_elements = complete_doc.get("extracted_elements")
    if not isinstance(extracted_elements, dict):
        return ""

    text_blocks = extracted_elements.get("text_blocks")
    if not isinstance(text_blocks, list):
        return ""

    parts: list[str] = []
    for block in text_blocks:
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or "").strip()
        if text:
            parts.append(text)

    return "\n\n".join(parts)


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


def build_section_path_ids(
    section_id: str,
    sections_by_id: dict[str, dict],
) -> list[str]:
    """
    Build the full ancestry chain of section IDs from root to the given section.

    This function walks the parent hierarchy using the sections_by_id lookup
    to construct a breadcrumb of section IDs suitable for filtering in Qdrant.

    Parameters
    ----------
    section_id : str
        The target section ID (e.g., "3.2.1" or "73c94e37-8f06-4721-9fcd-495ca176c3f3_section_7").
    sections_by_id : dict[str, dict]
        A dictionary mapping section_id → section node dict, where each node
        contains "parent_id" for hierarchy construction.

    Returns
    -------
    list[str]
        Ordered list of section IDs from root to target. For example:
        - "3.2.1" with parent "3.2" and grandparent "3" → ["3", "3.2", "3.2.1"]
        - "1" with no parents → ["1"]
        - non-existent ID → []

    Notes
    -----
    - Empty path returned if section_id is not in sections_by_id (missing parent).
    - Walks are bounded by the chain; circular parent references will truncate
      (when a parent is not found in sections_by_id, traversal stops).
    """
    path: list[str] = []
    current_id: Optional[str] = section_id
    visited: set[str] = set()

    while current_id:
        # Detect circular references and prevent infinite loops
        if current_id in visited:
            logger.warning(
                "build_section_path_ids: circular parent reference detected at %s; stopping traversal",
                current_id,
            )
            break
        visited.add(current_id)

        node = sections_by_id.get(current_id)
        if not node:
            # Missing node in hierarchy; silently stop traversal
            break

        path.insert(0, current_id)
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


def _is_reference_section_title(title: str) -> bool:
    title_norm = str(title or "").strip().lower()
    if not title_norm:
        return False
    return any(keyword in title_norm for keyword in _REFERENCE_SECTION_KEYWORDS)


def _is_reference_block(block: dict) -> bool:
    label = str(block.get("label") or "").strip().lower()
    section_name = str(block.get("section_title") or block.get("section") or "").strip().lower()
    text = str(block.get("text") or "").strip()

    if label in {"reference", "bibliography"}:
        return True
    if _is_reference_section_title(section_name):
        return True
    if text and re.match(r"^\s*(references|bibliography|works cited)\b", text, flags=re.I):
        return True
    return False


def _extract_reference_blocks(elements: Optional[ElementDict]) -> list[dict]:
    if not elements:
        return []

    explicit_refs = elements.get("references")
    if isinstance(explicit_refs, list) and explicit_refs:
        refs: list[dict] = []
        for item in explicit_refs:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            refs.append(item)
        if refs:
            return refs

    refs: list[dict] = []
    for block in elements.get("text_blocks", []):
        if not isinstance(block, dict):
            continue
        if not _is_reference_block(block):
            continue
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        refs.append(block)
    return refs


def _join_reference_text(reference_blocks: list[dict]) -> str:
    if not reference_blocks:
        return ""

    seen: set[str] = set()
    ordered: list[str] = []
    for block in reference_blocks:
        text = str(block.get("text") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)

    return "\n".join(ordered).strip()


def _strip_reference_text(text: str, reference_blocks: list[dict]) -> str:
    cleaned = text or ""
    if not cleaned or not reference_blocks:
        return cleaned

    for block in reference_blocks:
        ref_text = str(block.get("text") or "").strip()
        if len(ref_text) < 20:
            continue
        cleaned = cleaned.replace(ref_text, "")

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


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
            Directory where ``_complete.json`` and optional ``_fulltext.txt`` live.
            Inferred from *hierarchy_json_path*'s parent when omitted.
        pdf_path : Path, optional
            Original PDF.  When provided, PyMuPDF is used for per-page text;
            otherwise fallback text is loaded from fulltext.txt or complete.json.

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
        source_file_name = f"{document_id}_complete.json"
        if pdf_path and Path(pdf_path).exists():
            page_texts = _extract_pages_pymupdf(Path(pdf_path))
            if page_texts:
                source_file_name = Path(pdf_path).name

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
            # Fallback: segment text sidecar by section headers.
            fallback_text, fallback_source = self._load_fallback_full_text(
                document_id,
                output_dir,
            )
            if fallback_text:
                source_file_name = fallback_source
                section_texts = _segment_fulltext_by_sections(
                    fallback_text,
                    all_section_nodes,
                )
                if not any(section_texts.values()):
                    logger.warning(
                        "Section-aware segmentation failed for %s; using whole-document fallback",
                        document_id,
                    )
                    return self._fallback_full_text_chunks(document_id, output_dir)
            else:
                logger.warning(
                    "Neither PDF pages nor fallback text found for %s; returning empty chunk list",
                    document_id,
                )
                return []

        # ── Load extracted elements from complete.json ────────────────────────
        extracted_elements = self._load_extracted_elements(document_id, output_dir)
        reference_blocks = _extract_reference_blocks(extracted_elements)

        # ── Produce chunks ────────────────────────────────────────────────────
        chunks: list[Chunk] = []
        chunk_index = 0

        # Process in reading_order for deterministic output
        ordered_nodes = sorted(all_section_nodes, key=lambda n: n.get("reading_order", 0))

        for node in ordered_nodes:
            section_id = node["section_id"]
            text = section_texts.get(section_id, "").strip()
            is_reference_section = _is_reference_section_title(node.get("title", ""))

            if is_reference_section:
                reference_text = _join_reference_text(reference_blocks)
                if reference_text and reference_text not in text:
                    text = f"{text}\n\n{reference_text}".strip() if text else reference_text
            else:
                text = _strip_reference_text(text, reference_blocks)

            if not text or len(text) < CHUNK_MIN_CHARS:
                continue  # skip empty / near-empty sections

            section_path = _build_section_path(section_id, sections_by_id)
            section_path_ids = build_section_path_ids(section_id, sections_by_id)

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
                    section_path_ids,
                    node.get("parent_id"),
                    node.get("page_start"),
                    node.get("page_end"),
                    source_file_name,
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
                    section_path_ids,
                    node.get("parent_id"),
                    node.get("page_start"),
                    node.get("page_end"),
                    source_file_name,
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
                            section_path_ids=section_path_ids,
                            parent_section_id=node.get("parent_id"),
                            page_start=node.get("page_start"),
                            page_end=node.get("page_end"),
                            element_ids=element_ids,
                            source_file=source_file_name,
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
    def _load_fallback_full_text(document_id: str, output_dir: Path) -> tuple[str, str]:
        """
        Load fallback text from sidecar artifacts.

        Priority:
        1) ``<document_id>_fulltext.txt``
        2) Reconstructed text from ``<document_id>_complete.json``
        """
        fulltext_path = output_dir / f"{document_id}_fulltext.txt"
        if fulltext_path.exists():
            full_text = fulltext_path.read_text(encoding="utf-8").strip()
            if full_text:
                return full_text, fulltext_path.name

        complete_path = output_dir / f"{document_id}_complete.json"
        if complete_path.exists():
            try:
                complete_doc = _load_complete(complete_path)
                reconstructed = _full_text_from_complete(complete_doc).strip()
                if reconstructed:
                    logger.info(
                        "Using reconstructed full text from %s",
                        complete_path,
                    )
                    return reconstructed, complete_path.name
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to reconstruct fallback text from %s (%s)",
                    complete_path,
                    exc,
                )

        return "", ""

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
            complete = _load_complete(complete_path)
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
        section_path_ids: list[str],
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
            section_path_ids=section_path_ids,
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
        section_path_ids: list[str],
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
            section_path_ids=section_path_ids,
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
        Last-resort: chunk full document text without section context.
        Used when hierarchy is empty/missing or section segmentation fails.
        """
        full_text, source_file_name = self._load_fallback_full_text(document_id, output_dir)
        full_text = full_text.strip()
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
                source_file=source_file_name,
            )
            for i, w in enumerate(windows)
            if len(w) >= CHUNK_MIN_CHARS
        ]


def chunk_paper(
    sections: list[dict],
    paper_id: str,
    chunk_size: int = COARSE_CHUNK_SIZE,
    overlap: int = COARSE_CHUNK_OVERLAP,
    model_name: str = DENSE_MODEL,
) -> list[Chunk]:
    """
    Chunk pre-extracted sections into Qdrant-ready payloads with section hierarchy.

    This function takes a list of section dictionaries (typically from extraction)
    and splits their text content into chunks, producing payloads with full
    section context (ID, title, path, parent, depth) for section-aware retrieval.

    Parameters
    ----------
    sections : list[dict]
        List of section dictionaries. Each dict should contain:
        - section_id: Unique section identifier (str, e.g. "3.2.1" or UUID-based)
        - original_name: Section heading text (str)
        - text: Section body text (str)
        - parent_id: ID of parent section, or None for root (str or None)
        - level: Section depth in hierarchy (int, 1 = top-level) [optional]
        - numbering: Section numeric identifier (str, optional, e.g. "3.2.1")

    paper_id : str
        Unique identifier for the paper/document these sections belong to.

    chunk_size : int
        Maximum tokens per chunk. Defaults to COARSE_CHUNK_SIZE (400).

    overlap : int
        Number of tokens to overlap between consecutive chunks. Defaults to
        COARSE_CHUNK_OVERLAP (60).

    model_name : str
        HuggingFace model name for tokenization. Defaults to DENSE_MODEL
        (bge-small-en-v1.5).

    Returns
    -------
    list[Chunk]
        Ordered list of Chunk objects ready for embedding and Qdrant upsert.
        Each chunk carries section context: section_id, title, path (ancestry),
        parent_section_id, depth, and paper_id.

    Notes
    -----
    - Builds a sections_by_id lookup first for O(1) parent traversal.
    - Uses section numbering (if available) as canonical section_id in chunks.
    - Falls back to provided section_id if numbering is absent.
    - Text chunks smaller than CHUNK_MIN_CHARS are discarded.
    - Section text is split using TokenAwareSplitter for token-accurate boundaries.
    - Chunk IDs are deterministic (uuid5) based on paper_id and chunk index.

    Example
    -------
    >>> sections = [
    ...     {
    ...         "section_id": "sec_1",
    ...         "original_name": "Introduction",
    ...         "numbering": "1",
    ...         "text": "This paper introduces...",
    ...         "parent_id": None,
    ...         "level": 1,
    ...     },
    ...     {
    ...         "section_id": "sec_2",
    ...         "original_name": "Related Work",
    ...         "numbering": "2",
    ...         "text": "Prior research has...",
    ...         "parent_id": None,
    ...         "level": 1,
    ...     },
    ... ]
    >>> chunks = chunk_paper(sections, paper_id="paper-uuid-123")
    >>> len(chunks) > 0
    True
    >>> chunks[0].paper_id
    'paper-uuid-123'
    """
    splitter = TokenAwareSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        model_name=model_name,
    )

    # Build sections_by_id for O(1) parent lookup during path building
    sections_by_id: dict[str, dict] = {s["section_id"]: s for s in sections}

    chunks: list[Chunk] = []
    chunk_index = 0

    for section in sections:
        section_id = section.get("section_id", "")
        text = (section.get("text") or "").strip()

        # Skip empty sections
        if not text or len(text) < CHUNK_MIN_CHARS:
            continue

        # Use numbering as canonical section_id if available; fall back to section_id
        canonical_section_id = section.get("numbering") or section_id

        # Build section path (ancestry chain using internal IDs)
        section_path_ids = build_section_path_ids(section_id, sections_by_id)
        
        # Build canonical path using numbering for display
        canonical_path = (
            [sections_by_id[sid].get("numbering") or sid for sid in section_path_ids if sid in sections_by_id]
            if section_path_ids
            else []
        )

        # Compute depth from path length
        depth = len(section_path_ids)

        # Split section text into chunks
        windows = splitter.split(text)

        for window in windows:
            if len(window) < CHUNK_MIN_CHARS:
                continue

            chunk_uuid = str(
                uuid.uuid5(uuid.NAMESPACE_DNS, f"{paper_id}:{chunk_index}")
            )

            chunks.append(
                Chunk(
                    chunk_id=chunk_uuid,
                    document_id=paper_id,
                    content=window,
                    content_type="text",
                    token_count=splitter.count_tokens(window),
                    chunk_index=chunk_index,
                    chunk_level="coarse",
                    section_id=canonical_section_id,
                    section_title=section.get("original_name", ""),
                    section_level=section.get("level", 1),
                    section_numbering=section.get("numbering"),
                    section_path=canonical_path,
                    section_path_ids=canonical_path,  # Use numbering-based ancestry for ID filtering
                    parent_section_id=section.get("parent_id"),
                    element_ids=[],
                    source_file=None,
                )
            )
            chunk_index += 1

    logger.info(
        "chunk_paper: produced %d chunks from %d sections for paper %s",
        len(chunks),
        len(sections),
        paper_id,
    )
    return chunks


def _flatten_sections(sections: list[dict]) -> list[dict]:
    """Recursively flatten nested sections list."""
    result = []
    for s in sections:
        result.append(s)
        result.extend(_flatten_sections(s.get("sections", [])))
    return result


# ── Demo: in-memory section scoping test (no Qdrant required) ──────────────────

def demo_section_scope_filtering():
    """
    Demonstrate section-aware chunk filtering without Qdrant.

    This function creates an in-memory document hierarchy (sections 3, 3.2, 3.2.1)
    and a set of sample chunks with their respective section_path_ids. It then
    shows how filtering works:

    - Querying for section "3" includes all chunks in 3, 3.2, 3.2.1 (parent scope)
    - Querying for section "3.2" includes chunks in 3.2, 3.2.1 (intermediate scope)
    - Querying for section "3.2.1" includes only chunks in 3.2.1 (leaf scope)

    This filtering mirrors the behavior of retrieve_with_section_scope() which
    uses the section_path_ids field in Qdrant payloads.

    Example Output
    ~~~~~~~~~~~~~~
    ::

        ✓ Section 3 (parent): matched 7 chunks (includes descendants)
        ✓ Section 3.2 (intermediate): matched 5 chunks (includes descendants)
        ✓ Section 3.2.1 (leaf): matched 2 chunks (exactly this section)

    Notes
    -----
    - This demo does NOT require Qdrant Cloud connectivity.
    - It shows that parent sections automatically include descendant chunks.
    - Use this test to validate the section_path_ids field structure and
      filtering logic before submitting chunks to Qdrant.
    """
    logger.info("🔬 Running demo: section scope filtering (no Qdrant required)")

    # ── Create sample in-memory chunks with section hierarchies ──────────────
    sample_chunks = [
        # Section 3 chunks
        {"id": "chunk_3_1", "content": "Section 3 intro", "section_id": "3", "section_path_ids": ["3"]},
        {"id": "chunk_3_2", "content": "Section 3 main text", "section_id": "3", "section_path_ids": ["3"]},

        # Section 3.2 chunks
        {"id": "chunk_3.2_1", "content": "Section 3.2 intro", "section_id": "3.2", "section_path_ids": ["3", "3.2"]},
        {"id": "chunk_3.2_2", "content": "Section 3.2 details", "section_id": "3.2", "section_path_ids": ["3", "3.2"]},
        {"id": "chunk_3.2_3", "content": "Section 3.2 more details", "section_id": "3.2", "section_path_ids": ["3", "3.2"]},

        # Section 3.2.1 chunks
        {"id": "chunk_3.2.1_1", "content": "Section 3.2.1 content", "section_id": "3.2.1", "section_path_ids": ["3", "3.2", "3.2.1"]},
        {"id": "chunk_3.2.1_2", "content": "Section 3.2.1 more content", "section_id": "3.2.1", "section_path_ids": ["3", "3.2", "3.2.1"]},

        # Section 4 chunks (different parent)
        {"id": "chunk_4_1", "content": "Section 4 intro", "section_id": "4", "section_path_ids": ["4"]},
    ]

    # ── Test cases: (query_section_id, expected_count, description) ──────────
    test_cases = [
        ("3", 7, "Parent section (should include descendants 3, 3.2, 3.2.1)"),
        ("3.2", 5, "Intermediate section (should include descendants 3.2, 3.2.1)"),
        ("3.2.1", 2, "Leaf section (should include only 3.2.1)"),
        ("4", 1, "Different section (should include only 4)"),
    ]

    logger.info("📊 Testing section scope filtering with %d sample chunks", len(sample_chunks))

    all_passed = True
    for query_section_id, expected_count, description in test_cases:
        # Filter chunks whose section_path_ids contains the query_section_id
        matched_chunks = [
            c for c in sample_chunks
            if query_section_id in c["section_path_ids"]
        ]
        actual_count = len(matched_chunks)
        passed = actual_count == expected_count

        status = "✓" if passed else "✗"
        logger.info(
            "  %s Section %s (%s): matched %d chunks (expected %d)",
            status,
            query_section_id,
            description,
            actual_count,
            expected_count,
        )

        if not passed:
            all_passed = False
            logger.error(
                "    FAILED: Expected %d chunks but got %d",
                expected_count,
                actual_count,
            )
            for c in matched_chunks:
                logger.debug("      - %s (section_path_ids=%s)", c["id"], c["section_path_ids"])

    if all_passed:
        logger.info("✅ All section scope filtering tests PASSED")
    else:
        logger.error("❌ Some section scope filtering tests FAILED")

    return all_passed


if __name__ == "__main__":
    """Run demo test when module is executed."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    demo_section_scope_filtering()
