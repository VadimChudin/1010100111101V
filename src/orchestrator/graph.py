"""Build the agent state machine."""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from src.orchestrator.nodes import executor, planner, reviewer, should_revise
from src.orchestrator.state import AgentState


def build_graph(checkpointer: object | None = None):
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner)
    builder.add_node("executor", executor)
    builder.add_node("reviewer", reviewer)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "executor")
    builder.add_edge("executor", "reviewer")
    builder.add_conditional_edges("reviewer", should_revise, {"executor": "executor", "end": END})
    return builder.compile(checkpointer=checkpointer or MemorySaver())

agent_graph = build_graph()
