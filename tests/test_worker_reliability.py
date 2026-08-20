from __future__ import annotations

import pytest

from src.queueing.run_queue import RunJob, RunQueue
from src.queueing.worker import RunWorker
from src.storage.run_store import SQLiteRunStore


@pytest.mark.asyncio
async def test_expired_lease_is_recovered_or_exhausted(tmp_path):
    store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    await store.create_run("recoverable", "user", "Recover this")
    assert await store.claim_run("recoverable", lease_seconds=0)
    recovered = await store.recover_runs(max_attempts=3, limit=10)
    assert [run.id for run in recovered.queued] == ["recoverable"]
    assert (await store.get_run("recoverable")).status == "queued"

    await store.create_run("exhausted", "user", "Stop this")
    assert await store.claim_run("exhausted", lease_seconds=0)
    exhausted = await store.recover_runs(max_attempts=1, limit=10)
    assert [run.id for run in exhausted.exhausted] == ["exhausted"]
    assert (await store.get_run("exhausted")).status == "failed"


@pytest.mark.asyncio
async def test_worker_failure_returns_durable_job_to_queue(monkeypatch, tmp_path):
    from src.queueing import worker as worker_module

    async def fail_run(*_args, **_kwargs):
        raise RuntimeError("transient")

    monkeypatch.setattr(worker_module, "run_agent", fail_run)
    store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    queue = RunQueue("redis://127.0.0.1:1/0")
    worker = RunWorker(queue, store)
    job = RunJob(run_id="retry", user_id="user", task="Retry me")
    await store.create_run(job.run_id, job.user_id, job.task)

    await worker.execute(job)

    run = await store.get_run(job.run_id)
    assert run.status == "queued"
    assert run.attempt_count == 1
    assert (await queue.dequeue(timeout_s=1)).run_id == job.run_id
    assert any(event["type"] == "run.retry_scheduled" for event in await store.get_events(job.run_id))


@pytest.mark.asyncio
async def test_existing_runs_schema_migrates_before_lease_index_creation(tmp_path):
    import sqlite3

    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task TEXT NOT NULL, status TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '', plan_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    store = SQLiteRunStore(str(database))
    await store.initialize()
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(runs)")}
    assert {"attempt_count", "lease_expires_at", "last_error"}.issubset(columns)
    assert "idx_runs_status_lease" in indexes


@pytest.mark.asyncio
async def test_periodic_recovery_skips_normally_queued_runs(tmp_path):
    store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    await store.create_run("queued", "user", "Await delivery")

    recovered = await store.recover_runs(max_attempts=3, limit=10, include_queued=False)

    assert recovered.queued == []
    assert (await store.get_run("queued")).status == "queued"
