"""FastAPI app exposing paper storage endpoints for the frontend."""

from __future__ import annotations

import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.extraction.extraction import extract_pdf
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
    references = store.get_references_for_paper_id(paper_id)
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
        "references": references,
        "text_blocks": text_blocks,
    }


@app.post("/api/papers/upload")
def upload_paper(file: UploadFile = File(...)) -> Dict[str, Any]:
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Missing file name")

    is_pdf_name = filename.lower().endswith(".pdf")
    is_pdf_type = (file.content_type or "").lower() == "application/pdf"
    if not (is_pdf_name or is_pdf_type):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    upload_dir = Path(__file__).resolve().parents[2] / "temp_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    temp_pdf_path = upload_dir / f"{uuid4().hex}_{safe_name}"

    try:
        with temp_pdf_path.open("wb") as out_file:
            shutil.copyfileobj(file.file, out_file)

        # Ensure extraction module can see the same DB config used by this API.
        if not os.getenv("POSTGRES_DSN"):
            os.environ["POSTGRES_DSN"] = _resolve_postgres_dsn()

        extraction_result = extract_pdf(temp_pdf_path, output_dir="input")
        db_result = extraction_result.get("database") or {}
        paper_id = db_result.get("paper_id")
        if paper_id is None:
            raise HTTPException(
                status_code=500,
                detail=f"Upload processed but not stored in database: {db_result.get('reason', 'unknown')}",
            )

        store = _make_store()
        paper = store.get_paper_by_id(int(paper_id))
        if not paper:
            raise HTTPException(status_code=500, detail="Paper persisted but could not be fetched")

        return {
            "paper": paper,
            "database": {
                "stored": bool(db_result.get("stored", False)),
                "paper_id": int(paper_id),
                "paper_name": db_result.get("paper_name"),
                "reason": db_result.get("reason"),
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {exc}") from exc
    finally:
        try:
            file.file.close()
        except Exception:
            pass
        try:
            if temp_pdf_path.exists():
                temp_pdf_path.unlink()
        except Exception:
            pass
