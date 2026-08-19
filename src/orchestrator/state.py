from __future__ import annotations
from typing import TypedDict, Any

class AgentState(TypedDict, total=False):
    run_id: str
    user_id: str
    task: str
    messages: list[dict[str, Any]]
    plan: dict[str, Any] | None
    current_step: int
    tool_results: list[dict[str, Any]]
    review: dict[str, Any] | None
    events: list[dict[str, Any]]
    status: str
    iteration: int
    error: str | None
