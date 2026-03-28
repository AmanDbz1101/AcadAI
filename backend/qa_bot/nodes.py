from langchain_core.messages import AIMessage, SystemMessage, trim_messages
from langchain_groq import ChatGroq
try:
    from .state import ChatState
    from .retriever import retrieve
except ImportError:
    from state import ChatState
    from retriever import retrieve

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

    # 2. Retrieve relevant chunks (same pipeline as main RAG retrieval)
    chunks = retrieve(
        query,
        document_id=state.get("document_id"),
        allowed_sections=state.get("allowed_sections") or None,
    )
    context = "\n\n---\n\n".join(chunks) if chunks else "No relevant chunks found."

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

    return {"messages": [AIMessage(content=response.content)]}
