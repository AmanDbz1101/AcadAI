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
    return {"papers": papers}


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

    return {
        "paper": paper,
        "sections": normalized_sections,
        "tables": tables,
        "images": images,
        "references": references,
        "text_blocks": text_blocks,
    }


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
