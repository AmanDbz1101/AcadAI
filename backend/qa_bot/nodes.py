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

Your job is to help the user understand a research paper they are actively reading.

You have access to retrieved chunks from the paper below. Use them as your 
primary source of truth. You may also use your own knowledge to clarify 
concepts, provide background, or fill gaps — but always make it clear when 
you are going beyond the paper.

If the retrieved chunks do not contain enough information to answer confidently,
say so honestly rather than guessing.

Keep answers focused, clear, and grounded.
"""


def chat_node(state: ChatState) -> dict:
    """
    Single node: retrieve → build prompt → call LLM → return response.
    """
    # 1. Get the latest user message
    last_message = state["messages"][-1]
    query = last_message.content

    pinned = state.get("pinned_sections") or None
    allowed_sections = state.get("allowed_sections") or []
    section_scope = pinned if pinned is not None else allowed_sections or None

    # 2. Retrieve relevant chunks (same pipeline as main RAG retrieval)
    retrieved_chunks = retrieve_with_metadata(
        query,
        document_id=state.get("document_id"),
        allowed_sections=section_scope,
        pinned_sections=pinned,
    )
    if pinned is not None:
        filtered_chunks = [
            chunk
            for chunk in retrieved_chunks
            if (chunk.get("metadata") or {}).get("section_title") in pinned
        ]

        if not filtered_chunks:
            section_names = ", ".join(pinned)
            message = (
                "The selected section(s) -- "
                f"{section_names} -- do not contain "
                "information relevant to your question. "
                "Try selecting a different section or ask without a section filter."
            )
            return {
                "messages": [AIMessage(content=message)],
                "retrieved_chunks": [],
                "answer": message,
                "sources": [],
                "scoped": True,
                "found_in_scope": False,
            }

        retrieved_chunks = filtered_chunks
    chunk_texts = [str(chunk.get("content") or "").strip() for chunk in retrieved_chunks]
    chunk_texts = [text for text in chunk_texts if text]
    context = "\n\n---\n\n".join(chunk_texts) if chunk_texts else "No relevant chunks found."

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
        content=f"RETRIEVED CONTEXT FROM PAPER:\n\n{context}"
    )
    system = SystemMessage(content=SYSTEM_PROMPT)
    messages_to_send = [system, context_injection] + trimmed

    # 5. Call Groq
    response = llm.invoke(messages_to_send)

    return {
        "messages": [AIMessage(content=response.content)],
        "retrieved_chunks": retrieved_chunks,
    }
