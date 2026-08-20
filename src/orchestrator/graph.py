from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from src.config import get_settings

from .state import AgentState
from .nodes import planner_node, executor_node, reviewer_node

try:
    from langgraph.graph import StateGraph, END
except ImportError:  # pragma: no cover
    StateGraph = None
    END = "__end__"


def build_graph():
    if StateGraph is None:
        return None
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("reviewer", reviewer_node)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "reviewer")
    graph.add_edge("reviewer", END)
    return graph.compile()


async def run_agent(
    task: str,
    run_id: str,
    user_id: str = "anonymous",
    event_sink: Callable[[dict], Awaitable[None]] | None = None,
) -> AgentState:
    initial: AgentState = {
        "run_id": run_id,
        "user_id": user_id,
        "task": task,
        "messages": [],
        "events": [{"type": "run.started", "payload": {"run_id": run_id}}],
        "tool_results": [],
        "iteration": 0,
        "status": "queued",
    }

    async def execute() -> AgentState:
        if event_sink is not None:
            # Persist node events immediately so an interrupted run retains
            # its progress and can be diagnosed or retried durably.
            state = initial
            for node in (planner_node, executor_node, reviewer_node):
                prior_events = len(state.get("events", []))
                state = {**state, **(await node(state))}
                for event in state.get("events", [])[prior_events:]:
                    await event_sink(event)
            return state

        app = build_graph()
        if app is not None:
            return await app.ainvoke(initial)
        state = await planner_node(initial)
        state = {**initial, **state}
        state = {**state, **(await executor_node(state))}
        return {**state, **(await reviewer_node(state))}

    return await asyncio.wait_for(execute(), timeout=get_settings().agent_run_timeout_s)
