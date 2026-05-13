from langchain_core.messages import AIMessage, SystemMessage, trim_messages
from langchain_groq import ChatGroq
try:
    from .state import ChatState
    from .retriever import retrieve_with_metadata
except ImportError:
    from state import ChatState
    from retriever import retrieve_with_metadata

# --- LLM ------------------------------------------------------------
llm = ChatGroq(
    model="llama-3.3-70b-versatile",   # swap to any groq model you prefer
    temperature=0.2,
)

# How many recent messages to keep in context (system msg not counted)
MAX_MESSAGES = 10

SYSTEM_PROMPT = """You are a research paper reading assistant.
Use retrieved paper chunks as the primary source of truth.

Response rules:
1. Start with a direct answer.
2. Keep answers concise and grounded in retrieved context.
3. Do not include per-bullet source citations in the answer body.
4. Do not include footer lines such as "For deeper understanding...".
5. If the answer depends on one dominant section, append one final line only:
   Source Section: <section title>
6. Never use filler openers such as "Certainly" or "Great question".
"""


def _normalize_section_label(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _chunk_section_candidates(chunk: dict) -> list[str]:
    metadata = chunk.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    candidates: list[str] = []
    for value in (
        chunk.get("section_title"),
        metadata.get("section_title"),
        metadata.get("section"),
    ):
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    section_path = metadata.get("section_path")
    if isinstance(section_path, list):
        for item in section_path:
            if isinstance(item, str) and item.strip():
                candidates.append(item.strip())

    return candidates


def _filter_chunks_by_allowed_sections(chunks: list, allowed_sections: list[str]) -> list:
    allowed_norm = {
        _normalize_section_label(section)
        for section in allowed_sections
        if isinstance(section, str) and section.strip()
    }
    if not allowed_norm:
        return chunks

    filtered = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        candidates = _chunk_section_candidates(chunk)
        candidate_norm = {_normalize_section_label(value) for value in candidates if value}

        matched = False
        for cand in candidate_norm:
            for allowed in allowed_norm:
                if cand == allowed or cand in allowed or allowed in cand:
                    matched = True
                    break
            if matched:
                break

        if matched:
            filtered.append(chunk)
    return filtered


def _format_chunks_as_context(chunks: list) -> str:
    if not chunks:
        return "No relevant content found in the paper."

    formatted = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        section = (
            chunk.get("section_title")
            or metadata.get("section_title")
            or metadata.get("section")
            or (metadata.get("section_path")[-1] if isinstance(metadata.get("section_path"), list) and metadata.get("section_path") else "")
            or "Unlabeled Section"
        )
        page = metadata.get("page_start") or metadata.get("page_number") or ""
        text = (
            chunk.get("text")
            or chunk.get("content")
            or chunk.get("payload", {}).get("text")
            or str(chunk)
        )

        page_str = f", p.{page}" if page else ""
        header = f"[{i}] Section: {section}{page_str}"
        formatted.append(f"{header}\n{text.strip()}")

    return "\n\n".join(formatted)


def _normalize_section_label(value: str) -> str:
    normalized = " ".join(str(value or "").strip().lower().split())
    if normalized.endswith("ies") and len(normalized) > 4:
        return normalized[:-3] + "y"
    if normalized.endswith("s") and len(normalized) > 4:
        return normalized[:-1]
    return normalized


def chat_node(state: ChatState) -> dict:
    """
    Single node: retrieve → build prompt → call LLM → return response.
    With fallback: if section filter yields 0 chunks, fall back to unfiltered retrieval.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 1. Get the latest user message
    last_message = state["messages"][-1]
    query = last_message.content

    pinned = state.get("pinned_sections") or None
    allowed_sections = state.get("allowed_sections") or []
    section_scope = pinned if pinned is not None else allowed_sections or None

    # 2. Retrieve relevant chunks (same pipeline as main RAG retrieval)
    allowed_sections = [
        section
        for section in (state.get("allowed_sections") or [])
        if isinstance(section, str) and section.strip()
    ]

    chunks = retrieve_with_metadata(
        query,
        document_id=state.get("document_id"),
        allowed_sections=allowed_sections or None,
    )

    # Enforce soft section scoping for chat focus mode: filter if possible, but fall back if needed.
    if allowed_sections:
        filtered_chunks = _filter_chunks_by_allowed_sections(chunks, allowed_sections)
        
        # Log diagnostics for debugging section matching
        if chunks:
            section_values = set()
            for chunk in chunks[:3]:
                metadata = chunk.get("metadata") or {}
                section_values.add(str(metadata.get("section_title", "")).strip())
            logger.info(
                f"Section filter: requested={allowed_sections}, "
                f"filtered={len(filtered_chunks)}/{len(chunks)} chunks, "
                f"sample chunk sections={section_values}"
            )
        
        if filtered_chunks:
            # Section filter succeeded, use filtered results
            chunks = filtered_chunks
        else:
            # Section filter returned 0 chunks: use unfiltered retrieval as fallback
            logger.warning(
                f"Section filter returned 0 chunks for sections={allowed_sections}, "
                f"falling back to unfiltered retrieval (have {len(chunks)} chunks)"
            )
            # Continue with unfiltered chunks instead of returning "not found"

    context = _format_chunks_as_context(chunks)

    # 3. Trim conversation history to last N messages
    trimmed = trim_messages(
        state["messages"],
        max_tokens=MAX_MESSAGES,
        token_counter=len,          # counts messages, not tokens
        strategy="last",
        include_system=False,
    )

    # 4. Build final message list: system + context injection + history
    context_injection = SystemMessage(
        content=(
            "RETRIEVED CONTEXT FROM PAPER:\n"
            "The following excerpts were retrieved from the paper "
            "based on your question. Each excerpt is labeled with "
            "its source section and page number.\n\n"
            f"{context}\n\n"
            "When answering, reference these sections by name "
            "where relevant."
        )
    )
    system = SystemMessage(content=SYSTEM_PROMPT)
    messages_to_send = [system, context_injection] + trimmed

    # 5. Call Groq
    response = llm.invoke(messages_to_send)

    return {
        "messages": [AIMessage(content=response.content)],
        "retrieved_chunks": chunks,
    }
