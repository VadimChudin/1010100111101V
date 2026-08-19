from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Any

from src.config import get_settings

try:  # pragma: no cover - import availability is environment-dependent
    import redis.asyncio as redis
except ImportError:  # pragma: no cover
    redis = None


QUEUE_KEY = "agent-platform:runs"


@dataclass(frozen=True)
class RunJob:
    run_id: str
    user_id: str
    task: str

    @classmethod
    def from_payload(cls, payload: str | bytes | dict[str, Any]) -> "RunJob":
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        if isinstance(payload, str):
            payload = json.loads(payload)
        return cls(run_id=str(payload["run_id"]), user_id=str(payload["user_id"]), task=str(payload["task"]))


class RunQueue:
    """A minimal single-worker queue, with Redis preferred in production.

    The durable ``runs`` table remains authoritative. Redis supplies wake-up and
    cross-process hand-off; development and unit tests work without a Redis
    service through the local queue fallback.
    """

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis: Any | None = None
        self._fallback: asyncio.Queue[RunJob] = asyncio.Queue()

    async def initialize(self) -> None:
        if self._redis is not None or redis is None:
            return
        candidate = redis.from_url(self.redis_url, decode_responses=True)
        try:
            await candidate.ping()
        except Exception:
            await candidate.aclose()
            return
        self._redis = candidate

    async def enqueue(self, job: RunJob) -> None:
        await self.initialize()
        if self._redis is not None:
            await self._redis.rpush(QUEUE_KEY, json.dumps(asdict(job), ensure_ascii=False))
            return
        await self._fallback.put(job)

    async def dequeue(self, timeout_s: int = 5) -> RunJob | None:
        await self.initialize()
        if self._redis is not None:
            item = await self._redis.blpop(QUEUE_KEY, timeout=timeout_s)
            return RunJob.from_payload(item[1]) if item is not None else None
        try:
            return await asyncio.wait_for(self._fallback.get(), timeout=timeout_s)
        except TimeoutError:
            return None

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


_queue: RunQueue | None = None


def get_run_queue() -> RunQueue:
    global _queue
    if _queue is None:
        _queue = RunQueue(get_settings().redis_url)
    return _queue
