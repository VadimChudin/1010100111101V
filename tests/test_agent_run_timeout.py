from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.orchestrator import graph


@pytest.mark.asyncio
async def test_run_agent_applies_absolute_deadline(monkeypatch):
    async def slow_planner(_state):
        await asyncio.sleep(0.05)
        return {}

    monkeypatch.setattr(graph, "planner_node", slow_planner)
    monkeypatch.setattr(graph, "get_settings", lambda: SimpleNamespace(agent_run_timeout_s=0.01))

    with pytest.raises(TimeoutError):
        await graph.run_agent("deadline test", "run", event_sink=lambda _event: asyncio.sleep(0))
