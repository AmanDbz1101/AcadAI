"""FastAPI app exposing paper storage endpoints for the frontend."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from backend.extraction.extraction import extract_pdf, generate_reading_guide_state
from backend.extraction.persistence import PostgresPaperStore
from backend.extraction.technical_terms import (
    extract_technical_terms_for_bundle,
    get_term_context_text,
    set_llm_definition_override,
)
from backend.rag.prompts import qa_prompt
from config import MIN_RELEVANCE_THRESHOLD


AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-auth-secret-change-me")
AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "86400"))
logger = logging.getLogger(__name__)

QUESTIONS_LONG_POLL_SECONDS = float(os.getenv("QUESTIONS_LONG_POLL_SECONDS", "20"))
QUESTIONS_LONG_POLL_INTERVAL_SECONDS = float(os.getenv("QUESTIONS_LONG_POLL_INTERVAL_SECONDS", "0.4"))


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class GenerateAnswerRequest(BaseModel):
    force_regenerate: bool = False


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


def _build_qa_context_from_chunks(chunks: List[Dict[str, Any]], max_chunks: int = 2) -> str:
    context_parts: List[str] = []
    for idx, chunk in enumerate(chunks[:max_chunks], 1):
        content = str(chunk.get("content") or chunk.get("text") or "").strip()
        metadata = chunk.get("metadata") or {}
        section_title = str(metadata.get("section_title") or metadata.get("section") or "").strip()
        if not content:
            continue
        if section_title:
            context_parts.append(f"[{idx}] Section: {section_title}\n{content}")
        else:
            context_parts.append(f"[{idx}]\n{content}")
    return "\n\n".join(context_parts)


def _build_sections_for_guide(store: PostgresPaperStore, paper_id: int) -> List[Dict[str, Any]]:
    rows = store.get_sections_for_paper_id(paper_id)
    normalized: List[Dict[str, Any]] = []
    for idx, row in enumerate(sorted(rows, key=lambda r: r.get("section_key") or ""), 1):
        normalized.append(
            {
                "id": str(row.get("id") or idx),
                "title": row.get("original_name") or f"Section {idx}",
                "level": int(row.get("level") or 1),
                "page_start": int(row.get("page_start") or 1),
                "stats": row.get("stats_json") or {},
            }
        )
    return normalized


def _build_full_text_for_guide(store: PostgresPaperStore, paper_id: int) -> str:
    blocks = store.get_text_blocks_for_paper_id(paper_id)
    parts: List[str] = []
    for block in blocks:
        text = str(block.get("text_content") or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _build_questions_for_persistence(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    question_section_pairs = state.get("question_section_pairs") or []
    per_question_results = state.get("per_question_results") or []
    qa_results = state.get("qa_results") or []

    by_question_payload: Dict[str, Dict[str, Any]] = {}
    for payload in per_question_results:
        question = str(payload.get("question") or "").strip()
        if question and question not in by_question_payload:
            by_question_payload[question] = payload

    by_question_answer: Dict[str, Dict[str, Any]] = {}
    for entry in qa_results:
        question = str(entry.get("question") or "").strip()
        if question and question not in by_question_answer:
            by_question_answer[question] = entry

    questions_to_store: List[Dict[str, Any]] = []
    for pair in question_section_pairs:
        question_text = str(pair.get("question") or "").strip()
        if not question_text:
            continue

        payload = by_question_payload.get(question_text) or {}
        answer_row = by_question_answer.get(question_text) or {}
        answer_text = answer_row.get("answer")
        status = str(answer_row.get("status") or ("completed" if answer_text else "pending"))

        questions_to_store.append(
            {
                "question_text": question_text,
                "scoped_sections": pair.get("sections") or [],
                "retrieval_payload": payload,
                "status": status,
                "answer_text": answer_text,
                "confidence": answer_row.get("confidence"),
                "error_message": None,
            }
        )

    return questions_to_store


def _compute_retrieval_payload_for_question(
    *,
    paper: Dict[str, Any],
    question_text: str,
    scoped_sections: List[str],
) -> Dict[str, Any]:
    # Keep retrieval behavior aligned with rag.graph by using its internal helpers.
    from rag import graph as rag_graph

    pipeline = rag_graph._get_retrieval_pipeline()
    document_id = str(paper.get("document_uuid") or "")
    if document_id:
        hierarchy_path = Path("output") / f"{document_id}_hierarchy.json"
        if hierarchy_path.exists():
            pipeline.index(
                hierarchy_json_path=hierarchy_path,
                output_dir=Path("output"),
                pdf_path=None,
            )

    hits, retrieval_meta = rag_graph._retrieve_for_question(
        pipeline=pipeline,
        question=question_text,
        step_sections=scoped_sections,
        document_id=document_id,
    )

    hits = rag_graph._dedupe_results(hits)
    hits = [chunk for chunk in hits if not rag_graph._is_reference_result(chunk)]
    filtered_hits = [
        chunk for chunk in hits if rag_graph._result_score(chunk) >= MIN_RELEVANCE_THRESHOLD
    ]
    if len(filtered_hits) < 2:
        filtered_hits = hits[:2]

    deduped_hits = rag_graph._dedupe_near_identical_chunks(filtered_hits)
    final_hits = deduped_hits[: rag_graph.QA_TOP_K]

    return {
        "question": question_text,
        "sections": scoped_sections,
        "resolved_sections": retrieval_meta["resolved_sections"],
        "expanded_queries": retrieval_meta["expanded_queries"],
        "chunk_level": retrieval_meta["chunk_level"],
        "chunks": [rag_graph._result_to_dict(r) for r in final_hits],
    }


def _resolve_hierarchy_artifact(document_uuid: str) -> Optional[Path]:
    if not document_uuid:
        return None
    candidate_dirs = [Path("input"), Path("output")]
    for base_dir in candidate_dirs:
        candidate = base_dir / f"{document_uuid}_hierarchy.json"
        if candidate.exists():
            return candidate
    return None


def _index_paper_in_qdrant(*, document_uuid: str, pdf_path: Path) -> Dict[str, Any]:
    """
    Index an uploaded paper in Qdrant using its generated hierarchy artifact.

    Returns a status payload without raising, so upload can still succeed even
    if vector indexing fails.
    """
    from rag import graph as rag_graph

    if not document_uuid:
        return {"indexed": False, "reason": "missing_document_uuid"}

    hierarchy_path = _resolve_hierarchy_artifact(document_uuid)
    if hierarchy_path is None:
        return {
            "indexed": False,
            "reason": "missing_hierarchy_artifact",
            "hierarchy_path": f"input/{document_uuid}_hierarchy.json or output/{document_uuid}_hierarchy.json",
        }

    try:
        pipeline = rag_graph._get_retrieval_pipeline()
        result = pipeline.index(
            hierarchy_json_path=hierarchy_path,
            output_dir=hierarchy_path.parent,
            pdf_path=pdf_path,
        )
        return {
            "indexed": True,
            "skipped": bool(getattr(result, "skipped", False)),
            "chunks": int(getattr(result, "total_chunks", 0) or 0),
            "collection": str(getattr(result, "collection_name", "")),
            "document_id": str(getattr(result, "document_id", document_uuid)),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Qdrant indexing failed for document_uuid=%s", document_uuid)
        return {"indexed": False, "reason": str(exc)}


def _remove_local_artifacts(document_uuid: str, source_pdf_path: Optional[str]) -> Dict[str, Any]:
    """Delete local extraction artifacts related to a document UUID."""
    removed_files: List[str] = []
    errors: List[str] = []

    if document_uuid:
        for base_dir in [Path("input"), Path("output")]:
            for artifact in base_dir.glob(f"{document_uuid}_*"):
                try:
                    if artifact.is_file():
                        artifact.unlink(missing_ok=True)
                        removed_files.append(str(artifact))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{artifact}: {exc}")

    if source_pdf_path:
        try:
            workspace_root = Path(__file__).resolve().parents[2]
            pdfs_root = (workspace_root / "pdfs").resolve()
            source_path = Path(str(source_pdf_path)).expanduser().resolve()
            if source_path.is_file() and str(source_path).startswith(str(pdfs_root)):
                source_path.unlink(missing_ok=True)
                removed_files.append(str(source_path))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source_pdf_path}: {exc}")

    return {
        "removed_files": removed_files,
        "errors": errors,
    }


def _delete_qdrant_document_points(document_uuid: str) -> Dict[str, Any]:
    if not document_uuid:
        return {
            "deleted": True,
            "reason": "missing_document_uuid_skipped",
            "document_id": document_uuid,
        }
    try:
        from rag.retrieval.indexing.qdrant_store import QdrantStoreManager

        manager = QdrantStoreManager()
        was_indexed = manager.document_is_indexed(document_uuid)
        removed = manager.delete_document_points(document_uuid)
        deleted = bool(removed) or not was_indexed
        return {
            "deleted": deleted,
            "was_indexed": bool(was_indexed),
            "collection": manager.collection_name,
            "document_id": document_uuid,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed deleting Qdrant points for document_uuid=%s", document_uuid)
        return {"deleted": False, "reason": str(exc), "document_id": document_uuid}


def _guide_status_from_row(guide_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not guide_row:
        return {"status": "missing", "error": None, "updated_at": None}

    plan = guide_row.get("guide_plan_json") if isinstance(guide_row.get("guide_plan_json"), dict) else {}
    explicit_status = str(plan.get("status") or "").strip().lower()
    if explicit_status in {"pending", "ready", "failed"}:
        status = explicit_status
    else:
        guide_json = guide_row.get("guide_json")
        status = "ready" if isinstance(guide_json, dict) and guide_json else "pending"

    return {
        "status": status,
        "error": plan.get("error"),
        "updated_at": guide_row.get("updated_at"),
    }


def _generate_and_store_reading_guide(paper_id: int) -> None:
    try:
        if not os.getenv("POSTGRES_DSN"):
            os.environ["POSTGRES_DSN"] = _resolve_postgres_dsn()

        store = _make_store()
        paper = store.get_paper_by_id(paper_id)
        if not paper:
            raise RuntimeError("Paper not found")

        sections = _build_sections_for_guide(store, paper_id)
        full_text = _build_full_text_for_guide(store, paper_id)
        result_state = generate_reading_guide_state(
            title=str(paper.get("title") or paper.get("paper_name") or ""),
            abstract=str(paper.get("abstract") or ""),
            sections=sections,
            full_text=full_text,
            defer_answer_generation=True,
            skip_retrieve_and_qa=True,
        )

        reading_guide = result_state.get("reading_guide") or {}
        if not isinstance(reading_guide, dict) or not reading_guide:
            raise RuntimeError("Guide workflow completed without a reading guide")

        guide_plan = result_state.get("reading_guide_plan")
        plan_payload = guide_plan if isinstance(guide_plan, dict) else {}
        plan_payload = {**plan_payload, "status": "ready", "error": None}

        question_section_pairs = result_state.get("question_section_pairs") or []
        questions_to_store = _build_questions_for_persistence(result_state)
        store.upsert_paper_guide(
            paper_id=paper_id,
            document_uuid=paper.get("document_uuid"),
            guide_json=reading_guide,
            guide_plan_json=plan_payload,
            question_section_pairs=question_section_pairs,
        )
        store.replace_paper_questions(
            paper_id=paper_id,
            document_uuid=paper.get("document_uuid"),
            questions=questions_to_store,
        )
        logger.info("Reading guide generated for paper_id=%s", paper_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed background reading guide generation for paper_id=%s", paper_id)
        try:
            store = _make_store()
            paper = store.get_paper_by_id(paper_id)
            store.upsert_paper_guide(
                paper_id=paper_id,
                document_uuid=(paper or {}).get("document_uuid"),
                guide_json={},
                guide_plan_json={"status": "failed", "error": str(exc)},
                question_section_pairs=[],
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist failed guide status for paper_id=%s", paper_id)


class GenerateAnswerRequest(BaseModel):
    force_regenerate: bool = False


class GenerateTermDefinitionRequest(BaseModel):
    term: str


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


def _generate_term_definition_with_llm(
    *,
    term: str,
    context_sentence: str,
    paper_title: str,
) -> str:
    llm = ChatGroq(
        model=os.getenv("QA_ANSWER_MODEL", "llama-3.3-70b-versatile"),
        temperature=0.2,
    )
    prompt = (
        f'Define the technical term "{term}" for a research-paper reader.\n\n'
        f"Paper title: {paper_title}\n"
        f"Context sentence: {context_sentence or 'N/A'}\n\n"
        "Return exactly 1-2 concise sentences, no bullets, no preamble."
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return str(response.content or "").strip()


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


@app.get("/api/cms/papers")
def cms_list_papers(
    limit: int = 200,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Dict[str, Any]:
    """Backend-only CMS endpoint for listing stored papers."""
    user_id = _require_auth_user_id(authorization)
    store = _make_store()
    papers = store.list_papers_for_user(user_id=user_id, limit=limit)
    items = [
        {
            **paper,
            "pdf_url": f"/api/papers/{paper['id']}/pdf",
            "bundle_url": f"/api/papers/{paper['id']}/bundle",
            "delete_url": f"/api/cms/papers/{paper['id']}",
        }
        for paper in papers
    ]
    return {
        "count": len(items),
        "papers": items,
    }


@app.delete("/api/cms/papers/{paper_id}")
def cms_delete_paper(
    paper_id: int,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Dict[str, Any]:
    """
    Backend-only CMS endpoint to remove a paper.

    Semantics:
    - Removes the caller's access link.
    - If no users remain linked to the paper, deletes DB rows, Qdrant points,
      and local extraction artifacts.
    """
    user_id = _require_auth_user_id(authorization)
    store = _make_store()

    qdrant_cleanup = {"deleted": False, "reason": "not_run"}

    def _qdrant_predelete(document_uuid: str) -> bool:
        nonlocal qdrant_cleanup
        qdrant_cleanup = _delete_qdrant_document_points(document_uuid)
        return bool(qdrant_cleanup.get("deleted"))

    result = store.delete_paper_for_user(
        user_id=user_id,
        paper_id=paper_id,
        before_global_delete=_qdrant_predelete,
    )
    if not result.get("deleted"):
        reason = result.get("reason")
        if reason == "paper_not_found":
            raise HTTPException(status_code=404, detail="Paper not found")
        if reason == "access_not_found":
            raise HTTPException(status_code=403, detail="You do not have access to this paper")
        if reason == "qdrant_delete_failed":
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Delete aborted because Qdrant cleanup failed",
                    "paper_id": paper_id,
                    "qdrant": qdrant_cleanup,
                },
            )
        raise HTTPException(status_code=500, detail=f"Delete failed: {reason}")

    if not bool(result.get("paper_deleted")):
        qdrant_cleanup = {"deleted": False, "reason": "skipped_not_globally_deleted"}

    file_cleanup = {"removed_files": [], "errors": ["skipped_not_globally_deleted"]}

    if bool(result.get("paper_deleted")):
        file_cleanup = _remove_local_artifacts(
            document_uuid=str(result.get("document_uuid") or ""),
            source_pdf_path=result.get("source_pdf_path"),
        )

    return {
        "paper_id": paper_id,
        "deleted": True,
        "paper_deleted": bool(result.get("paper_deleted")),
        "reason": result.get("reason"),
        "remaining_links": int(result.get("remaining_links") or 0),
        "qdrant": qdrant_cleanup,
        "artifacts": file_cleanup,
    }


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
    
    guide_row = store.get_paper_guide_for_paper_id(paper_id)
    guide_status = _guide_status_from_row(guide_row)
    technical_terms = extract_technical_terms_for_bundle(paper_with_url, normalized_sections)

    # Legacy papers may still have reading_guide directly on papers table.
    reading_guide = paper_with_url.pop("reading_guide", None)
    if guide_status["status"] == "ready" and isinstance((guide_row or {}).get("guide_json"), dict):
        reading_guide = guide_row.get("guide_json")

    # Only use synthesized fallback when no explicit guide state exists.
    # For pending/failed states we return no guide so frontend can render live status.
    if (
        (not isinstance(reading_guide, dict) or not reading_guide)
        and guide_status["status"] == "missing"
    ):
        metadata_json = paper_with_url.get("metadata_json")
        inference = metadata_json.get("inference") if isinstance(metadata_json, dict) else {}
        paper_type_hint = inference.get("paper_type") if isinstance(inference, dict) else None
        reading_guide = _build_fallback_reading_guide(
            paper_title=str(paper_with_url.get("paper_name") or paper_with_url.get("title") or ""),
            sections=normalized_sections,
            paper_type_hint=str(paper_type_hint) if paper_type_hint else None,
        )
        guide_status = {"status": "ready", "error": None, "updated_at": None}
    
    return {
        "paper": paper_with_url,
        "sections": normalized_sections,
        "technical_terms": technical_terms,
        "tables": tables,
        "images": images,
        "references": references,
        "text_blocks": text_blocks,
        "reading_guide": reading_guide,
        "guide_status": guide_status,
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


@app.get("/api/papers/{paper_id}/guide")
def get_paper_guide(
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

    guide_row = store.get_paper_guide_for_paper_id(paper_id)
    questions = store.list_paper_questions_for_paper_id(paper_id)
    guide_status = _guide_status_from_row(guide_row)
    return {
        "paper": paper,
        "guide": guide_row,
        "guide_status": guide_status,
        "questions": questions,
    }


@app.post("/api/papers/upload")
def upload_paper(
    background_tasks: BackgroundTasks,
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

        extraction_result = extract_pdf(
            temp_pdf_path,
            output_dir="input",
            generate_reading_guide=False,
        )
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

        # Keep vector DB aligned with uploaded papers so retrieval reflects
        # newly ingested documents immediately.
        qdrant_index = _index_paper_in_qdrant(
            document_uuid=str(paper.get("document_uuid") or ""),
            pdf_path=pdf_storage_path,
        )

        queued = False
        existing_guide_row = store.get_paper_guide_for_paper_id(int(paper_id))
        current_status = _guide_status_from_row(existing_guide_row)
        has_legacy_guide = isinstance(paper.get("reading_guide"), dict) and bool(paper.get("reading_guide"))

        if current_status["status"] != "ready" and not has_legacy_guide:
            store.upsert_paper_guide(
                paper_id=int(paper_id),
                document_uuid=paper.get("document_uuid"),
                guide_json={},
                guide_plan_json={"status": "pending", "error": None},
                question_section_pairs=[],
            )
            background_tasks.add_task(_generate_and_store_reading_guide, int(paper_id))
            queued = True

        guide_status = (
            {"status": "pending", "error": None, "updated_at": None}
            if queued
            else (
                current_status
                if current_status["status"] != "missing"
                else {"status": "ready" if has_legacy_guide else "pending", "error": None, "updated_at": None}
            )
        )

        return {
            "paper": paper,
            "database": {
                "stored": bool(db_result.get("stored", False)),
                "paper_id": int(paper_id),
                "paper_name": db_result.get("paper_name"),
                "reason": db_result.get("reason"),
            },
            "qdrant": qdrant_index,
            "pdf_id": pdf_uuid,
            "guide_status": guide_status,
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


@app.get("/api/papers/{paper_id}/questions")
def get_paper_questions(paper_id: int) -> Dict[str, Any]:
    store = _make_store()
    paper = store.get_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    deadline = time.monotonic() + max(0.0, QUESTIONS_LONG_POLL_SECONDS)
    questions: List[Dict[str, Any]] = []

    while True:
        questions = store.list_paper_questions_for_paper_id(paper_id)
        if questions:
            break

        guide_status = _guide_status_from_row(store.get_paper_guide_for_paper_id(paper_id))
        if guide_status["status"] != "pending":
            break

        if time.monotonic() >= deadline:
            break

        time.sleep(max(0.05, QUESTIONS_LONG_POLL_INTERVAL_SECONDS))

    return {"paper": paper, "questions": questions}


@app.post("/api/papers/{paper_id}/questions/{question_id}/generate")
def generate_answer_for_question(
    paper_id: int,
    question_id: int,
    payload: GenerateAnswerRequest,
) -> Dict[str, Any]:
    store = _make_store()

    paper = store.get_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    try:
        claimed = store.claim_question_for_generation(
            paper_id=paper_id,
            question_id=question_id,
            force_regenerate=payload.force_regenerate,
        )
    except ValueError as exc:
        if str(exc) == "question_not_found":
            raise HTTPException(status_code=404, detail="Question not found") from exc
        if str(exc) == "question_running":
            raise HTTPException(status_code=409, detail="Question answer generation already running") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if claimed.get("status") == "completed" and claimed.get("answer_text") and not payload.force_regenerate:
        return {"paper": paper, "question": claimed}

    question_text = str(claimed.get("question_text") or "").strip()
    retrieval_payload = claimed.get("retrieval_payload_json") or {}
    chunks = retrieval_payload.get("chunks") or []

    if not chunks and question_text:
        try:
            retrieval_payload = _compute_retrieval_payload_for_question(
                paper=paper,
                question_text=question_text,
                scoped_sections=claimed.get("scoped_sections_json") or [],
            )
            chunks = retrieval_payload.get("chunks") or []
            claimed = store.update_paper_question_retrieval_payload(
                paper_id=paper_id,
                question_id=question_id,
                retrieval_payload=retrieval_payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to compute retrieval payload on demand for paper_id=%s question_id=%s: %s",
                paper_id,
                question_id,
                exc,
            )

    context = _build_qa_context_from_chunks(chunks)

    try:
        if not context:
            answer = "No relevant content found."
            confidence = "LOW"
        else:
            llm = ChatGroq(
                model=os.getenv("QA_ANSWER_MODEL", "llama-3.3-70b-versatile"),
                temperature=0.3,
            )
            prompt = qa_prompt(
                query=question_text,
                context=context,
                metadata={
                    "paper_title": paper.get("title") or paper.get("paper_name") or "",
                    "category": (retrieval_payload.get("category") or ""),
                },
            )
            response = llm.invoke([HumanMessage(content=prompt)])
            answer = str(response.content or "").strip()
            confidence = "HIGH" if len(answer) > 100 else "MEDIUM"

        question_row = store.complete_paper_question(
            paper_id=paper_id,
            question_id=question_id,
            answer_text=answer,
            confidence=confidence,
        )
        return {"paper": paper, "question": question_row}
    except Exception as exc:  # noqa: BLE001
        store.fail_paper_question(
            paper_id=paper_id,
            question_id=question_id,
            error_message=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Answer generation failed: {exc}") from exc


@app.post("/api/papers/{paper_id}/technical-terms/generate")
def generate_technical_term_definition(
    paper_id: int,
    payload: GenerateTermDefinitionRequest,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Dict[str, Any]:
    user_id = _require_auth_user_id(authorization)
    store = _make_store()

    if not store.user_has_access_to_paper(user_id=user_id, paper_id=paper_id):
        raise HTTPException(status_code=403, detail="You do not have access to this paper")

    paper = store.get_paper_by_id(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    term = str(payload.term or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="term is required")

    sections = store.get_sections_for_paper_id(paper_id)
    text_blocks = store.get_text_blocks_for_paper_id(paper_id)
    section_text_links = store.get_section_text_blocks_for_paper_id(paper_id)

    section_text_map: Dict[int, List[str]] = defaultdict(list)
    for row in section_text_links:
        section_id = row.get("section_id")
        content = (row.get("text_content") or "").strip()
        if section_id and content:
            section_text_map[int(section_id)].append(content)

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
            }
        )

    context_sentence = get_term_context_text(paper, normalized_sections, term)

    try:
        definition = _generate_term_definition_with_llm(
            term=term,
            context_sentence=context_sentence,
            paper_title=str(paper.get("title") or paper.get("paper_name") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Definition generation failed: {exc}") from exc

    if not definition:
        raise HTTPException(status_code=500, detail="Definition generation returned empty content")

    term_payload = set_llm_definition_override(paper_id=paper_id, term=term, definition=definition)
    return {
        "paper": paper,
        "technical_term": {
            "term": term,
            **term_payload,
        },
    }
