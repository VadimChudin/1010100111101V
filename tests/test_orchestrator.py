"""Basic offline test for the planner-executor-reviewer flow."""
import pytest
from src.orchestrator.graph import build_graph
from src.orchestrator import nodes

class MockRouter:
    async def complete(self, messages, task=None, model=None):
        prompt = messages[-1]["content"]
        if "Create a concise" in prompt:
            return "1. Understand the request\n2. Draft the answer\n3. Check quality"
        if "Review this answer" in prompt:
            return "APPROVED"
        return "Mock execution result"

@pytest.mark.asyncio
async def test_planner_executor_reviewer_flow(monkeypatch):
    mock = MockRouter()
    monkeypatch.setattr(nodes, "OmniRouter", lambda: mock)
    graph = build_graph()
    result = await graph.ainvoke({"thread_id": "test", "user_message": "Сделай план", "events": [], "iteration": 0}, config={"configurable": {"thread_id": "test"}})
    assert result["status"] == "reviewed"
    assert result["plan"]
    assert result["execution_result"] == "Mock execution result"
    assert result["review"] == "APPROVED"
    assert [event["node"] for event in result["events"]] == ["planner", "executor", "reviewer"]
