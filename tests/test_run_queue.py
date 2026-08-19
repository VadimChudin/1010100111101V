from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from src.main import app
from src.queueing import RunJob, RunQueue, RunWorker
from src.storage.run_store import SQLiteRunStore


@pytest.mark.asyncio
async def test_worker_persists_incremental_events_and_completes_run(monkeypatch, tmp_path):
    from src.queueing import worker as worker_module

    store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    queue = RunQueue("redis://127.0.0.1:1/0")
    await store.create_run("run-1", "user-1", "Queue this task")

    async def fake_run_agent(task: str, run_id: str, user_id: str, event_sink):
        await event_sink({"type": "plan.created", "payload": {"goal": task}})
        await event_sink({"type": "review.updated", "payload": {"approved": True}})
        return {
            "status": "completed",
            "review": {"approved": True, "comment": "Completed from queue."},
            "plan": {"goal": task, "steps": []},
        }

    monkeypatch.setattr(worker_module, "run_agent", fake_run_agent)
    await RunWorker(queue, store).execute(RunJob("run-1", "user-1", "Queue this task"))

    stored = await store.get_run("run-1")
    events = await store.get_events("run-1")
    assert stored is not None and stored.status == "completed"
    assert [event["type"] for event in events] == ["run.started", "plan.created", "review.updated", "run.completed"]


@pytest.mark.asyncio
async def test_sse_replays_persisted_events_for_a_terminal_run(monkeypatch, tmp_path):
    from src.api import routes

    store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    await store.create_run("run-1", "user-1", "Replay timeline")
    await store.append_events("run-1", [{"type": "plan.created", "payload": {"goal": "Replay timeline"}}])
    await store.complete_run("run-1", "completed", "Done", {"goal": "Replay timeline", "steps": []})
    monkeypatch.setattr(routes, "get_run_store", lambda: store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/runs/run-1/stream")

    assert response.status_code == 200
    assert "id: 1" in response.text
    assert "event: timeline" in response.text
    assert '"type": "plan.created"' in response.text
    assert '"sequence": 1' in response.text
