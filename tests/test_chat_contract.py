import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.orchestrator.nodes import executor_node, parse_agent_plan


FENCED_PLAN = """```json
{
  "goal": "Return OK",
  "steps": [
    {
      "id": "reply",
      "title": "Prepare the response",
      "description": "Use the validated plan contract.",
      "command": "echo OK",
      "depends_on": []
    }
  ],
  "acceptance_criteria": ["The response is OK"]
}
```"""


def test_parser_accepts_json_wrapped_in_a_markdown_fence():
    plan = parse_agent_plan(FENCED_PLAN, "Return OK")

    assert plan.goal == "Return OK"
    assert plan.steps[0].id == "reply"
    assert plan.steps[0].command == "echo OK"
    assert plan.acceptance_criteria == ["The response is OK"]


@pytest.mark.asyncio
async def test_executor_skips_raw_shell_by_default_without_blocking_the_run(monkeypatch):
    monkeypatch.delenv("ENABLE_UNSAFE_SHELL", raising=False)
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        result = await executor_node(
            {
                "task": "Return OK",
                "plan": {
                    "goal": "Return OK",
                    "steps": [{"id": "reply", "title": "Reply", "command": "echo OK", "depends_on": []}],
                    "acceptance_criteria": [],
                },
                "events": [],
                "tool_results": [],
            }
        )

        assert result["tool_results"] == []
        assert result["status"] == "executed"
        assert result["events"][0] == {
            "type": "tool.blocked",
            "payload": {
                "step_id": "reply",
                "reason": "Raw shell commands are disabled until the typed tool policy is implemented.",
            },
        }
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_chat_endpoint_returns_public_plan_object_without_commands(monkeypatch):
    async def fake_run_agent(task: str, run_id: str, user_id: str):
        return {
            "status": "completed",
            "review": {"comment": "Done"},
            "plan": {
                "goal": task,
                "steps": [
                    {
                        "id": "step-1",
                        "title": "Validate contract",
                        "description": "Return a stable public payload.",
                        "command": "echo hidden",
                        "depends_on": [],
                    }
                ],
                "acceptance_criteria": ["The UI can render plan.steps"],
            },
            "events": [{"type": "plan.created"}],
        }

    monkeypatch.setattr("src.api.routes.run_agent", fake_run_agent)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat", json={"message": "Validate the contract"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["goal"] == "Validate the contract"
    assert payload["plan"]["steps"][0]["id"] == "step-1"
    assert "command" not in payload["plan"]["steps"][0]
    assert payload["events"] == [{"type": "plan.created"}]
