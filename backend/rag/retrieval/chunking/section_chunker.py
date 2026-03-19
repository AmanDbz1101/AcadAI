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

import json
import logging
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

            # Split the section text
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


def _flatten_sections(sections: list[dict]) -> list[dict]:
    """Recursively flatten nested sections list."""
    result = []
    for s in sections:
        result.append(s)
        result.extend(_flatten_sections(s.get("sections", [])))
    return result
