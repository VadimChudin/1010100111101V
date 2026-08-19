from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from src.main import app
from src.tools.serena import SerenaClient


@pytest.mark.asyncio
async def test_serena_client_is_read_only_and_uses_injected_transport():
    calls: list[tuple[str, dict]] = []

    async def transport(tool: str, arguments: dict):
        calls.append((tool, arguments))
        return {"ok": True, "tool": tool}

    client = SerenaClient(transport)
    result = await client.find_symbol("ToolGateway.invoke", "src/tools/gateway.py", include_body=True)

    assert client.available is True
    assert result["ok"] is True
    assert calls == [("find_symbol", {"name_path": "ToolGateway.invoke", "include_body": True, "relative_path": "src/tools/gateway.py"})]


@pytest.mark.asyncio
async def test_metrics_and_serena_status_are_exposed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/v1/healthz", headers={"X-Request-ID": "test-request"})
        status = await client.get("/v1/serena/status")
        metrics = await client.get("/v1/metrics")

    assert health.headers["x-request-id"] == "test-request"
    assert status.json()["mode"] == "read_only"
    assert status.json()["available"] is False
    assert any("GET /v1/healthz 200" == item["key"] for item in metrics.json()["requests"])
