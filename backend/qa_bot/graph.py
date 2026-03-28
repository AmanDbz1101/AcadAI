from langgraph.graph import StateGraph, START, END
try:
    from .state import ChatState
    from .nodes import chat_node
except ImportError:
    from state import ChatState
    from nodes import chat_node


def build_graph():
    builder = StateGraph(ChatState)

    builder.add_node("chat", chat_node)

    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)

    return builder.compile()


graph = build_graph()
