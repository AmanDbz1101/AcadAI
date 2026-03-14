"""FastAPI app exposing paper storage endpoints for the frontend."""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.extraction.persistence import PostgresPaperStore


def _resolve_postgres_dsn() -> str:
    explicit = os.getenv("POSTGRES_DSN")
    if explicit:
        return explicit

    host = os.getenv("POSTGRES_HOST") or os.getenv("PGHOST")
    port = os.getenv("POSTGRES_PORT") or os.getenv("PGPORT")
    dbname = os.getenv("POSTGRES_DB") or os.getenv("PGDATABASE")
    user = os.getenv("POSTGRES_USER") or os.getenv("PGUSER")
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD")

    if not all([host, port, dbname, user]):
        raise RuntimeError(
            "PostgreSQL configuration missing. Set POSTGRES_DSN or POSTGRES_HOST/PORT/DB/USER."
        )

    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    return f"postgresql://{user}@{host}:{port}/{dbname}"


def _make_store() -> PostgresPaperStore:
    return PostgresPaperStore(_resolve_postgres_dsn())


app = FastAPI(title="ResearchAgent Backend API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> Dict[str, Any]:
    try:
        store = _make_store()
        store.ensure_schema()
        papers = store.list_papers(limit=1)
        return {"status": "ok", "db": "connected", "sample_count": len(papers)}
    except Exception as exc:
        return {"status": "degraded", "db": "error", "error": str(exc)}


@app.get("/api/papers")
def list_papers(limit: int = 100) -> Dict[str, Any]:
    store = _make_store()
    papers = store.list_papers(limit=limit)
    return {"papers": papers}


@app.get("/api/papers/{paper_id}/bundle")
def get_paper_bundle(paper_id: int) -> Dict[str, Any]:
    store = _make_store()

    paper = store.get_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    sections = store.get_sections_for_paper_id(paper_id)
    text_blocks = store.get_text_blocks_for_paper_id(paper_id)
    tables = store.get_tables_for_paper_id(paper_id)
    images = store.get_images_for_paper_id(paper_id)
    section_text_links = store.get_section_text_blocks_for_paper_id(paper_id)

    # Compose readable section content by linked text blocks (fallback to per-page aggregation).
    section_text_map: Dict[int, List[str]] = defaultdict(list)
    for row in section_text_links:
        section_id = row.get("section_id")
        content = (row.get("text_content") or "").strip()
        if section_id and content:
            section_text_map[int(section_id)].append(content)

    # Fallback text by page number when section links are sparse.
    page_to_texts: Dict[int, List[str]] = defaultdict(list)
    for block in text_blocks:
        page = block.get("page_number")
        text = (block.get("text_content") or "").strip()
        if page is not None and text:
            page_to_texts[int(page)].append(text)

    sections_sorted = sorted(sections, key=lambda s: s.get("section_key") or "")
    normalized_sections: List[Dict[str, Any]] = []
    for idx, section in enumerate(sections_sorted):
        sid = int(section["id"])
        content_lines = section_text_map.get(sid, [])
        if not content_lines:
            page = int(section.get("page_start") or 1)
            content_lines = page_to_texts.get(page, [])

        normalized_sections.append(
            {
                "id": str(sid),
                "title": section.get("original_name") or f"Section {idx + 1}",
                "level": int(section.get("level") or 1),
                "page_start": int(section.get("page_start") or 1),
                "content": "\n\n".join(content_lines).strip(),
                "stats": section.get("stats_json") or {},
            }
        )

    return {
        "paper": paper,
        "sections": normalized_sections,
        "tables": tables,
        "images": images,
        "text_blocks": text_blocks,
    }
