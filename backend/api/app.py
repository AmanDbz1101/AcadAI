"""FastAPI app exposing paper storage endpoints for the frontend."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.extraction.extraction import extract_pdf
from backend.extraction.persistence import PostgresPaperStore


AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-auth-secret-change-me")
AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "86400"))


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _hash_password(password: str, salt_hex: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (password or "").encode("utf-8"),
        bytes.fromhex(salt_hex),
        200_000,
    )
    return digest.hex()


def _create_password_hash(password: str) -> tuple[str, str]:
    salt_hex = secrets.token_bytes(16).hex()
    return _hash_password(password, salt_hex), salt_hex


def _verify_password(password: str, salt_hex: str, stored_hash: str) -> bool:
    candidate = _hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, stored_hash)


def _create_token(user_id: int, email: str) -> str:
    payload = {
        "uid": int(user_id),
        "em": email,
        "exp": int(time.time()) + AUTH_TOKEN_TTL_SECONDS,
    }
    message = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), message, hashlib.sha256).digest()
    return f"{_b64url_encode(message)}.{_b64url_encode(signature)}"


def _parse_token(token: str) -> Dict[str, Any]:
    try:
        message_part, signature_part = token.split(".", 1)
        message = _b64url_decode(message_part)
        signature = _b64url_decode(signature_part)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    expected = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), message, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid token signature")

    try:
        payload = json.loads(message.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token payload") from exc

    if int(payload.get("exp") or 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="Token expired")
    if not payload.get("uid"):
        raise HTTPException(status_code=401, detail="Invalid token subject")

    return payload


def _extract_bearer_token(authorization: Optional[str]) -> str:
    value = (authorization or "").strip()
    if not value or not value.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = value[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


def _require_auth_user_id(authorization: Optional[str]) -> int:
    token = _extract_bearer_token(authorization)
    payload = _parse_token(token)
    return int(payload["uid"])


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


def _pick_sections_by_keywords(
    sections: List[Dict[str, Any]],
    keywords: List[str],
    limit: int = 3,
) -> List[str]:
    scored: List[tuple[int, str]] = []
    for section in sections:
        title = str(section.get("title") or section.get("original_name") or "").strip()
        if not title:
            continue
        normalized = title.lower()
        score = sum(1 for keyword in keywords if keyword in normalized)
        if score > 0:
            scored.append((score, title))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    selected = [title for _, title in scored[:limit]]
    if selected:
        return selected

    fallback_titles = [
        str(section.get("title") or section.get("original_name") or "").strip()
        for section in sections[:limit]
    ]
    return [title for title in fallback_titles if title]


def _build_fallback_reading_guide(
    paper_title: str,
    sections: List[Dict[str, Any]],
    paper_type_hint: Optional[str] = None,
) -> Dict[str, Any]:
    pass1_sections = _pick_sections_by_keywords(
        sections,
        ["abstract", "introduction", "conclusion", "overview"],
    )
    pass2_sections = _pick_sections_by_keywords(
        sections,
        ["method", "approach", "model", "architecture", "proof", "taxonomy"],
    )
    pass3_sections = _pick_sections_by_keywords(
        sections,
        ["result", "analysis", "discussion", "evaluation", "limitation"],
    )

    # Infer fallback paper type so pass key names align with guide schema variants.
    section_titles = " ".join(
        str(section.get("title") or section.get("original_name") or "").lower()
        for section in sections
    )
    hint = (paper_type_hint or "").strip().lower()
    if hint in {"theoretical", "theory", "proof"}:
        paper_type = "theoretical"
    elif hint in {"survey", "review", "literature_review", "meta_analysis"}:
        paper_type = "survey"
    elif hint in {"applied", "experimental", "empirical", "system"}:
        paper_type = "applied"
    elif any(token in section_titles for token in ["theorem", "lemma", "proof", "corollary"]):
        paper_type = "theoretical"
    elif any(token in section_titles for token in ["survey", "taxonomy", "landscape", "review"]):
        paper_type = "survey"
    else:
        paper_type = "applied"

    if paper_type == "theoretical":
        pass2_key = "pass2_proof_strategy"
        pass2_goal = "Understand the theorem structure, assumptions, and proof plan."
        pass2_questions = [
            "What is the proof strategy?",
            "Which assumptions are essential?",
        ]
        pass3_key = "pass3_deep_mathematical_analysis"
        pass3_goal = "Analyze proof details, rigor, and mathematical limitations."
    elif paper_type == "survey":
        pass2_key = "pass2_taxonomy_understanding"
        pass2_goal = "Understand the taxonomy and category-level comparisons."
        pass2_questions = [
            "How is the taxonomy organized?",
            "What distinguishes the categories?",
        ]
        pass3_key = "pass3_research_landscape_analysis"
        pass3_goal = "Analyze gaps, trends, and future research directions."
    else:
        pass2_key = "pass2_method_understanding"
        pass2_goal = "Understand methodology and technical approach."
        pass2_questions = [
            "What are the main components of the method?",
            "What assumptions are required?",
        ]
        pass3_key = "pass3_deep_analysis"
        pass3_goal = "Critically analyze evidence, results, and limitations."

    def _step_sections(section_names: List[str], index: int) -> List[str]:
        if not section_names:
            return []
        if len(section_names) >= 3:
            return [section_names[index]]
        # Ensure each step has at least one section even for short lists.
        return [section_names[min(index, len(section_names) - 1)]]

    return {
        "paper_title": paper_title or "Unknown Paper",
        "reading_strategy": {
            "method": "three_pass_method",
            "paper_type": paper_type,
            "estimated_total_time": "45-60 minutes",
        },
        "pass1_quick_scan": {
            "goal": "Build a high-level understanding of the paper.",
            "estimated_time": "10-15 minutes",
            "steps": [
                {
                    "step_number": 1,
                    "section_to_read": _step_sections(pass1_sections, 0),
                    "needs_figures": False,
                    "needs_tables": False,
                    "objective": "Identify the problem and context.",
                    "questions_to_answer": [
                        "What problem does this paper solve?",
                        "Why is this problem important?",
                    ],
                    "expected_output": "A concise statement of the paper's problem and motivation.",
                },
                {
                    "step_number": 2,
                    "section_to_read": _step_sections(pass1_sections, 1),
                    "needs_figures": False,
                    "needs_tables": False,
                    "objective": "Extract the core contribution and scope.",
                    "questions_to_answer": [
                        "What is the main contribution?",
                        "What is in scope vs out of scope?",
                    ],
                    "expected_output": "A short description of novelty and scope.",
                },
                {
                    "step_number": 3,
                    "section_to_read": _step_sections(pass1_sections, 2),
                    "needs_figures": False,
                    "needs_tables": False,
                    "objective": "Summarize claims and high-level outcomes.",
                    "questions_to_answer": [
                        "What key claims are made?",
                        "What headline outcomes are reported?",
                    ],
                    "expected_output": "A 2-3 sentence high-level paper summary.",
                }
            ],
        },
        pass2_key: {
            "goal": pass2_goal,
            "estimated_time": "15-20 minutes",
            "steps": [
                {
                    "step_number": 1,
                    "section_to_read": _step_sections(pass2_sections, 0),
                    "needs_figures": True,
                    "needs_tables": False,
                    "objective": "Understand the method components and assumptions.",
                    "questions_to_answer": pass2_questions,
                    "expected_output": "A component-level method breakdown.",
                },
                {
                    "step_number": 2,
                    "section_to_read": _step_sections(pass2_sections, 1),
                    "needs_figures": True,
                    "needs_tables": False,
                    "objective": "Trace the end-to-end flow of the approach.",
                    "questions_to_answer": [
                        "How does data flow through the method?",
                        "Which design choices are critical?",
                    ],
                    "expected_output": "A clear end-to-end explanation in your own words.",
                },
                {
                    "step_number": 3,
                    "section_to_read": _step_sections(pass2_sections, 2),
                    "needs_figures": True,
                    "needs_tables": True,
                    "objective": "Understand setup details used for evaluation.",
                    "questions_to_answer": [
                        "How is the method evaluated?",
                        "What baselines or comparisons are used?",
                    ],
                    "expected_output": "A summary of evaluation setup and comparisons.",
                }
            ],
        },
        pass3_key: {
            "goal": pass3_goal,
            "estimated_time": "20-25 minutes",
            "steps": [
                {
                    "step_number": 1,
                    "section_to_read": _step_sections(pass3_sections, 0),
                    "needs_figures": True,
                    "needs_tables": True,
                    "objective": "Evaluate whether the evidence supports the claims.",
                    "questions_to_answer": [
                        "Do the results support the claims?",
                        "Where is evidence strongest or weakest?",
                    ],
                    "expected_output": "An evidence-based judgment of claim validity.",
                },
                {
                    "step_number": 2,
                    "section_to_read": _step_sections(pass3_sections, 1),
                    "needs_figures": True,
                    "needs_tables": True,
                    "objective": "Probe robustness, edge cases, and limitations.",
                    "questions_to_answer": [
                        "What are the key limitations?",
                        "What failure modes or edge cases are likely?",
                    ],
                    "expected_output": "A concise limitations and risk assessment.",
                },
                {
                    "step_number": 3,
                    "section_to_read": _step_sections(pass3_sections, 2),
                    "needs_figures": False,
                    "needs_tables": False,
                    "objective": "Assess practical impact and next steps.",
                    "questions_to_answer": [
                        "What is practically useful from this work?",
                        "What follow-up experiments or research are needed?",
                    ],
                    "expected_output": "A final critical summary with actionable next steps.",
                }
            ],
        },
    }


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


@app.post("/api/auth/register")
def register(payload: RegisterRequest) -> Dict[str, Any]:
    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    store = _make_store()
    password_hash, password_salt = _create_password_hash(password)
    user = store.create_user(
        email=email,
        password_hash=password_hash,
        password_salt=password_salt,
        display_name=payload.display_name,
    )
    if user is None:
        raise HTTPException(status_code=409, detail="User already exists")

    user_safe = {
        "id": user["id"],
        "email": user["email"],
        "display_name": user.get("display_name"),
        "created_at": user.get("created_at"),
    }
    token = _create_token(int(user["id"]), str(user["email"]))
    return {"token": token, "user": user_safe}


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> Dict[str, Any]:
    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    store = _make_store()
    user = store.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not _verify_password(password, str(user["password_salt"]), str(user["password_hash"])):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_token(int(user["id"]), str(user["email"]))
    user_safe = {
        "id": user["id"],
        "email": user["email"],
        "display_name": user.get("display_name"),
        "created_at": user.get("created_at"),
    }
    return {"token": token, "user": user_safe}


@app.get("/api/auth/me")
def me(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> Dict[str, Any]:
    user_id = _require_auth_user_id(authorization)
    store = _make_store()
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"user": user}


@app.get("/api/papers")
def list_papers(
    limit: int = 100,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Dict[str, Any]:
    user_id = _require_auth_user_id(authorization)
    store = _make_store()
    papers = store.list_papers_for_user(user_id=user_id, limit=limit)
    # Add pdf_url to each paper
    papers_with_urls = [
        {**paper, "pdf_url": f"/api/papers/{paper['id']}/pdf"}
        for paper in papers
    ]
    return {"papers": papers_with_urls}


@app.get("/api/papers/{paper_id}/bundle")
def get_paper_bundle(
    paper_id: int,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Dict[str, Any]:
    user_id = _require_auth_user_id(authorization)
    store = _make_store()

    if not store.user_has_access_to_paper(user_id=user_id, paper_id=paper_id):
        raise HTTPException(status_code=403, detail="You do not have access to this paper")

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

    # Add pdf_url to paper object for frontend to fetch PDF
    paper_with_url = {
        **paper,
        "pdf_url": f"/api/papers/{paper_id}/pdf"
    }
    
    # Extract reading guide from paper object if available
    reading_guide = paper_with_url.pop("reading_guide", None)

    # If no guide is stored, synthesize a deterministic fallback guide from sections.
    # This keeps frontend behavior consistent for legacy papers.
    if not isinstance(reading_guide, dict) or not reading_guide:
        metadata_json = paper_with_url.get("metadata_json")
        inference = metadata_json.get("inference") if isinstance(metadata_json, dict) else {}
        paper_type_hint = inference.get("paper_type") if isinstance(inference, dict) else None
        reading_guide = _build_fallback_reading_guide(
            paper_title=str(paper_with_url.get("paper_name") or paper_with_url.get("title") or ""),
            sections=normalized_sections,
            paper_type_hint=str(paper_type_hint) if paper_type_hint else None,
        )
    
    return {
        "paper": paper_with_url,
        "sections": normalized_sections,
        "tables": tables,
        "images": images,
        "references": references,
        "text_blocks": text_blocks,
        "reading_guide": reading_guide,
    }


@app.get("/api/papers/{paper_id}/pdf")
def get_paper_pdf(
    paper_id: int,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    token: Optional[str] = None,
) -> FileResponse:
    """Serve the PDF file for a given paper ID. Accepts auth via header or query param."""
    # Try to get user_id from Authorization header; if not present, try token query param
    auth_header = authorization
    if not auth_header and token:
        auth_header = f"Bearer {token}"
    
    user_id = _require_auth_user_id(auth_header)
    store = _make_store()
    
    if not store.user_has_access_to_paper(user_id=user_id, paper_id=paper_id):
        raise HTTPException(status_code=403, detail="You do not have access to this paper")
    
    paper = store.get_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Primary source: use the exact persisted source path when available.
    source_pdf_path = paper.get("source_pdf_path")
    if source_pdf_path:
        source_path = Path(str(source_pdf_path)).expanduser().resolve()
        if source_path.exists() and source_path.is_file():
            print(f"[PDF_SERVE] Serving source_pdf_path: {source_path}")
            return FileResponse(
                path=source_path,
                filename=f"{paper.get('paper_name', 'paper')}.pdf",
                media_type="application/pdf",
                content_disposition_type="inline",
            )
    
    # Fallback: look for PDF in pdfs directory
    pdfs_dir = Path(__file__).resolve().parents[2] / "pdfs"
    doc_uuid = paper.get("document_uuid")
    
    # Try primary search: find by paper_name pattern
    pdf_files = []
    if pdfs_dir.exists():
        paper_name = (paper.get("paper_name") or "").strip()
        paper_name_tokens = [token.lower() for token in paper_name.replace("_", " ").split() if token]

        all_pdfs = list(pdfs_dir.glob("*.pdf"))

        # Try strict document UUID matching first.
        if doc_uuid:
            doc_uuid_str = str(doc_uuid)
            pdf_files = [
                p for p in all_pdfs if doc_uuid_str in p.name or doc_uuid_str[:8] in p.name
            ]

        # Then try fuzzy name-token matching for mismatched upload filenames.
        if not pdf_files and paper_name_tokens:
            def _name_matches(file_name: str) -> bool:
                lowered = file_name.lower()
                return sum(1 for t in paper_name_tokens if t in lowered) >= min(2, len(paper_name_tokens))

            pdf_files = [p for p in all_pdfs if _name_matches(p.name)]
    
    # If PDF found, serve it
    if pdf_files:
        pdf_path = pdf_files[0]
        print(f"[PDF_SERVE] Serving PDF: {pdf_path}")
        return FileResponse(
            path=pdf_path,
            filename=f"{paper.get('paper_name', 'paper')}.pdf",
            media_type="application/pdf",
            content_disposition_type="inline",
        )
    
    # Fallback: Look for extracted complete.json in input directory and convert to HTML
    print(f"[PDF_SERVE] PDF not found on disk, looking for extracted JSON for paper_id={paper_id}")
    input_dir = Path(__file__).resolve().parents[2] / "input"
    
    if input_dir.exists() and doc_uuid:
        # Search for extracted files matching this document's UUID
        base_name = f"{doc_uuid}_complete.json"
        complete_json_path = input_dir / base_name
        
        if complete_json_path.exists():
            print(f"[PDF_SERVE] Found extracted JSON, generating HTML: {complete_json_path}")
            import json
            
            try:
                with open(complete_json_path, 'r', encoding='utf-8') as f:
                    doc_data = json.load(f)
                
                # Build basic HTML from extracted content
                title = paper.get('paper_name', 'Document')
                abstract = doc_data.get('metadata', {}).get('abstract', '')
                
                # Extract text from various possible formats
                text_content = ''
                extracted_elements = doc_data.get('extracted_elements', [])
                for elem in extracted_elements[:500]:  # Limit to first 500 elements
                    if isinstance(elem, dict) and 'text' in elem:
                        text_content += elem['text'].strip() + '\n\n'
                
                if not text_content:
                    # Fallback to marked_text if available
                    text_content = '\n\n'.join([
                        md.get('text', '') for md in doc_data.get('marked_text', [])
                        if md.get('text', '').strip()
                    ])
                
                # Sanitize HTML content
                title_safe = title.replace('<', '&lt;').replace('>', '&gt;')
                abstract_safe = abstract.replace('<', '&lt;').replace('>', '&gt;')[:500]
                preview_text = text_content[:3000].replace('<', '&lt;').replace('>', '&gt;')
                
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title_safe}</title>
    <style>
        body {{ font-family: 'Georgia', serif; line-height: 1.8; margin: 0; padding: 0; background: #f9f9f9; }}
        .header {{ background: white; padding: 40px; border-bottom: 1px solid #e0e0e0; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 40px; min-height: 100vh; }}
        h1 {{ font-size: 28px; color: #000; margin: 0 0 20px 0; }}
        .subtitle {{ color: #666; font-size: 14px; margin: 0; }}
        .warning {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 15px; margin: 30px 0; color: #856404; }}
        .metadata {{ background: #f8f9fa; border-left: 4px solid #007bff; padding: 15px; margin: 20px 0; font-size: 13px; }}
        .content {{ margin-top: 40px; color: #333; white-space: pre-wrap; word-wrap: break-word; font-family: 'Segoe UI', sans-serif; }}
        .page-break {{ margin: 60px 0; border-top: 2px dashed #ccc; padding-top: 40px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title_safe}</h1>
        <p class="subtitle">Research Paper Viewer - Extracted Content Preview</p>
    </div>
    <div class="container">
        <div class="warning">
            <strong>⚠️ Extracted Content Preview:</strong><br/>
            The original PDF file is not available. This is an HTML rendering of extracted text and metadata. 
            For the complete reading experience with proper formatting and images, please re-upload the PDF file.
        </div>
        <div class="metadata">
            <strong>Paper ID:</strong> {paper_id} | <strong>Document UUID:</strong> {doc_uuid[:8]}...<br/>
            <strong>Status:</strong> Served as extracted text fallback
        </div>
        {f'<h2>Abstract</h2><p>{abstract_safe}</p>' if abstract_safe else ''}
        <div class="page-break"></div>
        <h2>Extracted Content Preview</h2>
        <div class="content">{preview_text}...</div>
        <div class="page-break"></div>
        <p style="text-align: center; color: #999; font-size: 12px; margin-top: 60px;">
            To view the complete document with proper formatting, images, and layout, please upload the original PDF file.
        </p>
    </div>
</body>
</html>"""
                
                from fastapi.responses import HTMLResponse
                return HTMLResponse(content=html_content)
            except Exception as e:
                print(f"[PDF_SERVE] Error generating HTML from JSON: {e}")
                import traceback
                traceback.print_exc()
    
    # No PDF found and no extracted JSON available
    print(f"[PDF_SERVE] No PDF or extracted data found. UUID={doc_uuid}, paper_name={paper.get('paper_name')}")
    raise HTTPException(
        status_code=404,
        detail="PDF file not available. Please re-upload the paper to get PDF viewing."
    )


@app.post("/api/papers/upload")
def upload_paper(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Dict[str, Any]:
    user_id = _require_auth_user_id(authorization)
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Missing file name")

    is_pdf_name = filename.lower().endswith(".pdf")
    is_pdf_type = (file.content_type or "").lower() == "application/pdf"
    if not (is_pdf_name or is_pdf_type):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    pdfs_dir = Path(__file__).resolve().parents[2] / "pdfs"
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    pdf_uuid = uuid4().hex
    pdf_storage_path = pdfs_dir / f"{pdf_uuid}_{safe_name}"
    temp_pdf_path = pdf_storage_path

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
        store.link_user_to_paper(user_id=user_id, paper_id=int(paper_id))
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
            "pdf_id": pdf_uuid,
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
