from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from src.events import get_event_broker
from src.orchestrator.graph import run_agent
from src.queueing.run_queue import RunJob, RunQueue
from src.storage import SQLiteRunStore


class RunWorker:
    """Single-consumer worker for durable queued agent runs."""

    def __init__(self, queue: RunQueue, store: SQLiteRunStore) -> None:
        self.queue = queue
        self.store = store

    async def _persist_and_notify(self, run_id: str, event: dict) -> None:
        await self.store.append_events(run_id, [event])
        get_event_broker().publish(run_id)

    async def execute(self, job: RunJob) -> None:
        if not await self.store.claim_run(job.run_id):
            return
        await self._persist_and_notify(job.run_id, {"type": "run.started", "payload": {"run_id": job.run_id}})

        async def event_sink(event: dict) -> None:
            await self._persist_and_notify(job.run_id, event)

        try:
            state = await run_agent(job.task, job.run_id, job.user_id, event_sink=event_sink)
            status = str(state.get("status") or "failed")
            answer = str(state.get("review", {}).get("comment", ""))
            await self.store.complete_run(job.run_id, status, answer, state.get("plan"))
            await self._persist_and_notify(
                job.run_id,
                {"type": "run.completed", "payload": {"status": status, "review": state.get("review", {})}},
            )
        except Exception:
            await self.store.complete_run(job.run_id, "failed", "", None)
            await self._persist_and_notify(
                job.run_id,
                {"type": "run.failed", "payload": {"message": "The agent run could not be completed."}},
            )

    async def serve(self, shutdown_requested: Callable[[], bool] | None = None) -> None:
        while shutdown_requested is None or not shutdown_requested():
            job = await self.queue.dequeue()
            if job is not None:
                await self.execute(job)


async def cancel_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
