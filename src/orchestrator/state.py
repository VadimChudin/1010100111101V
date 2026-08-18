"""Typed state shared by LangGraph nodes."""
from typing import Any, TypedDict

class AgentState(TypedDict, total=False):
    thread_id: str
    user_message: str
    metadata: dict[str, Any]
    plan: list[str]
    execution_result: str
    review: str
    status: str
    iteration: int
    events: list[dict[str, Any]]
    error: str
