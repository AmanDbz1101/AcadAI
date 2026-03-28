from langchain_core.messages import HumanMessage
try:
    from .graph import graph
except ImportError:
    from graph import graph

def run():
    print("Paper Chatbot — type 'quit' to exit\n")

    # State persists across turns within this session
    state = {"messages": [], "allowed_sections": []}

    while True:
        user_input = input("You: ").strip()

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            break

        # Append user message and invoke graph
        state["messages"].append(HumanMessage(content=user_input))
        result = graph.invoke(state)

        # Update state with full result (includes AI response)
        state = result

        # Print latest AI message
        print(f"\nAssistant: {state['messages'][-1].content}\n")


if __name__ == "__main__":
    run()
