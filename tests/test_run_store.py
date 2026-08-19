from __future__ import annotations

import pytest

from src.storage.run_store import SQLiteRunStore


@pytest.mark.asyncio
async def test_run_store_creates_completes_and_reads_a_run(tmp_path):
    store = SQLiteRunStore(str(tmp_path / "agent-state.db"))

    created = await store.create_run("run-1", "user-1", "Persist this task")
    await store.complete_run(
        "run-1",
        "completed",
        "Completed safely.",
        {"goal": "Persist this task", "steps": []},
    )
    stored = await store.get_run("run-1")

    assert created.status == "queued"
    assert stored is not None
    assert stored.user_id == "user-1"
    assert stored.status == "completed"
    assert stored.answer == "Completed safely."
    assert stored.plan == {"goal": "Persist this task", "steps": []}


@pytest.mark.asyncio
async def test_run_store_sequences_events_and_supports_cursor_reads(tmp_path):
    store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    await store.create_run("run-1", "user-1", "Inspect events")

    persisted = await store.append_events(
        "run-1",
        [
            {"type": "run.started", "payload": {"source": "test"}},
            {"type": "plan.created", "payload": {"steps": 2}},
            {"type": "review.updated", "payload": {"approved": True}},
        ],
    )
    after_first = await store.get_events("run-1", after_sequence=1)

    assert [event["sequence"] for event in persisted] == [1, 2, 3]
    assert [event["type"] for event in after_first] == ["plan.created", "review.updated"]
    assert all(event["created_at"] for event in after_first)
