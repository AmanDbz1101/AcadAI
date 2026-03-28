from typing import Annotated
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict, NotRequired


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]  # auto-appends, never overwrites
    allowed_sections: list[str]
    document_id: NotRequired[str]
