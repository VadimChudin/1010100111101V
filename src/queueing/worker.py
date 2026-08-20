from __future__ import annotations

import asyncio
from collections.abc import Callable

from src.config import get_settings
from src.events import get_event_broker
from src.observability import metrics
from src.orchestrator.graph import run_agent
from src.queueing.run_queue import RunJob, RunQueue
from src.storage import SQLiteRunStore


class RunWorker:
    """Durable single-service worker for SQLite-first deployments.

    Redis is used for wake-up delivery only. The runs table is authoritative, so
    a process restart can safely recover queued work and expired leases without
    executing a run twice.
    """

    def __init__(self, queue: RunQueue, store: SQLiteRunStore) -> None:
        self.queue = queue
        self.store = store
        self.settings = get_settings()
        self._stop = asyncio.Event()

    def request_shutdown(self) -> None:
        self._stop.set()

    async def _persist_and_notify(self, run_id: str, event: dict) -> None:
        await self.store.append_events(run_id, [event])
        get_event_broker().publish(run_id)

    async def _heartbeat(self, run_id: str, finished: asyncio.Event) -> None:
        while not finished.is_set():
            try:
                await asyncio.wait_for(finished.wait(), timeout=self.settings.worker_heartbeat_seconds)
            except TimeoutError:
                renewed = await self.store.renew_lease(run_id, self.settings.worker_lease_seconds)
                if not renewed:
                    return

    async def recover(self) -> None:
        recovery = await self.store.recover_runs(self.settings.worker_max_attempts, self.settings.worker_recovery_batch_size)
        for run in recovery.exhausted:
            metrics.record_worker("lease_exhausted")
            await self._persist_and_notify(run.id, {"type": "run.failed", "payload": {"message": "Run recovery exceeded its retry limit."}})
        for run in recovery.queued:
            await self._persist_and_notify(run.id, {"type": "run.recovered", "payload": {"attempt": run.attempt_count, "reason": "worker_restart_or_lease_expiry"}})
            try:
                await self.queue.enqueue(RunJob(run_id=run.id, user_id=run.user_id, task=run.task))
                metrics.record_worker("recovered")
            except Exception:
                # The durable queued status remains authoritative; the next
                # worker start will retry delivery rather than losing the run.
                metrics.record_worker("recovery_enqueue_failed")

    async def execute(self, job: RunJob) -> None:
        if not await self.store.claim_run(job.run_id, self.settings.worker_lease_seconds):
            return
        run = await self.store.get_run(job.run_id)
        attempt = run.attempt_count if run is not None else 1
        await self._persist_and_notify(job.run_id, {"type": "run.started", "payload": {"run_id": job.run_id, "attempt": attempt}})
        lease_finished = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(job.run_id, lease_finished), name=f"run-lease-{job.run_id}")

        async def event_sink(event: dict) -> None:
            await self._persist_and_notify(job.run_id, event)

        try:
            state = await run_agent(job.task, job.run_id, job.user_id, event_sink=event_sink)
            status = str(state.get("status") or "failed")
            answer = str(state.get("review", {}).get("comment", ""))
            await self.store.complete_run(job.run_id, status, answer, state.get("plan"))
            metrics.record_run(status)
            metrics.record_worker("completed")
            await self._persist_and_notify(job.run_id, {"type": "run.completed", "payload": {"status": status, "review": state.get("review", {}), "attempt": attempt}})
        except Exception as exc:
            retry = await self.store.release_for_retry(job.run_id, type(exc).__name__, self.settings.worker_max_attempts)
            if retry:
                metrics.record_worker("retry_scheduled")
                await self._persist_and_notify(job.run_id, {"type": "run.retry_scheduled", "payload": {"attempt": attempt, "max_attempts": self.settings.worker_max_attempts}})
                try:
                    await self.queue.enqueue(job)
                except Exception:
                    metrics.record_worker("retry_enqueue_failed")
            else:
                metrics.record_run("failed")
                metrics.record_worker("failed")
                await self._persist_and_notify(job.run_id, {"type": "run.failed", "payload": {"message": "The agent run could not be completed after bounded retries.", "attempt": attempt}})
        finally:
            lease_finished.set()
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    async def serve(self, shutdown_requested: Callable[[], bool] | None = None) -> None:
        await self.recover()
        while not self._stop.is_set() and (shutdown_requested is None or not shutdown_requested()):
            job = await self.queue.dequeue()
            if job is not None:
                await self.execute(job)


async def cancel_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
