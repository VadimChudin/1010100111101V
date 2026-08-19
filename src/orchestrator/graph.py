from __future__ import annotations

from collections.abc import Awaitable, Callable

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

    if event_sink is not None:
        # The explicit sequence makes each node's appended event observable as
        # soon as that node completes. The normal invocation keeps LangGraph as
        # the default execution engine for synchronous compatibility.
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
    state = {**state, **(await reviewer_node(state))}
    return state
