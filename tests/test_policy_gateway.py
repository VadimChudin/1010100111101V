from __future__ import annotations

import pytest

from src.config import get_settings
from src.policy import ApprovalMode, PolicyAction, PolicyEngine, RiskClass, ToolCall, ToolCallRequest
from src.storage.run_store import SQLiteRunStore
from src.tools.gateway import ToolGateway


@pytest.mark.asyncio
async def test_read_only_tool_auto_allows_and_secret_path_is_hard_denied(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    (tmp_path / "README.md").write_text("Visible content", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=value", encoding="utf-8")
    store = SQLiteRunStore(str(tmp_path / "state.db"))
    await store.create_run("run-1", "user-1", "Inspect workspace")
    gateway = ToolGateway(store)

    allowed = await gateway.invoke("run-1", ToolCallRequest(tool="read_file", arguments={"path": "README.md"}, approval_mode=ApprovalMode.PLAN))
    denied = await gateway.invoke("run-1", ToolCallRequest(tool="read_file", arguments={"path": ".env"}, approval_mode=ApprovalMode.PLAN))

    assert allowed.status == "completed"
    assert allowed.result["content"] == "Visible content"
    assert denied.status == "denied"
    assert denied.policy.hard_deny is True
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_confirm_each_creates_durable_approval_and_executes_exact_granted_edit(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    store = SQLiteRunStore(str(tmp_path / "state.db"))
    await store.create_run("run-1", "user-1", "Create a file")
    gateway = ToolGateway(store)

    proposed = await gateway.invoke(
        "run-1",
        ToolCallRequest(
            tool="create_file",
            arguments={"path": "notes/decision.md", "content": "Approved content"},
            approval_mode=ApprovalMode.CONFIRM_EACH,
        ),
    )

    assert proposed.status == "awaiting_approval"
    assert proposed.approval is not None
    persisted = await store.get_approval(proposed.approval.id)
    assert persisted is not None and persisted.status == "pending"

    resolved = await gateway.resolve(proposed.approval.id, approved=True, grant_scope="once")
    assert resolved is not None and resolved.status == "completed"
    assert (tmp_path / "notes" / "decision.md").read_text(encoding="utf-8") == "Approved content"
    events = await store.get_events("run-1")
    assert [event["type"] for event in events] == ["policy.decided", "approval.requested", "approval.granted", "tool.started", "tool.completed"]
    get_settings.cache_clear()


def test_policy_hard_denies_raw_shell_in_every_mode():
    decision = PolicyEngine().decide(
        ToolCall(tool="raw_shell", arguments={"command": "echo unsafe"}, risk=RiskClass.PRIVILEGED),
        ApprovalMode.ALL_APPROVALS_FOR_RUN,
    )

    assert decision.action == PolicyAction.DENY
    assert decision.hard_deny is True


@pytest.mark.asyncio
async def test_approval_api_executes_only_after_explicit_decision(monkeypatch, tmp_path):
    from httpx import ASGITransport, AsyncClient
    from src.api import routes
    from src.main import app

    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    store = SQLiteRunStore(str(tmp_path / "state.db"))
    await store.create_run("run-api", "user-1", "Approved edit")
    monkeypatch.setattr(routes, "get_run_store", lambda: store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        proposed = await client.post(
            "/v1/runs/run-api/tool-calls",
            json={
                "tool": "create_file",
                "arguments": {"path": "safe.txt", "content": "allowed once"},
                "approval_mode": "confirm_each",
            },
        )
        assert proposed.status_code == 200
        approval_id = proposed.json()["approval"]["id"]
        assert not (tmp_path / "safe.txt").exists()

        approved = await client.post(
            f"/v1/runs/run-api/approvals/{approval_id}/decision",
            json={"approved": True, "grant_scope": "once"},
        )

    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
    assert (tmp_path / "safe.txt").read_text(encoding="utf-8") == "allowed once"
    get_settings.cache_clear()
