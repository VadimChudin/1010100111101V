from __future__ import annotations

import asyncio
from collections import defaultdict


class RunEventBroker:
    """Best-effort notifier layered on top of durable SQLite events.

    SQLite remains the source of truth. Queues only wake local SSE connections;
    an SSE client can always resume from its last persisted sequence after a
    reconnect or a process restart.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[None]]] = defaultdict(set)

    def subscribe(self, run_id: str) -> asyncio.Queue[None]:
        subscriber: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers[run_id].add(subscriber)
        return subscriber

    def unsubscribe(self, run_id: str, subscriber: asyncio.Queue[None]) -> None:
        subscribers = self._subscribers.get(run_id)
        if subscribers is None:
            return
        subscribers.discard(subscriber)
        if not subscribers:
            self._subscribers.pop(run_id, None)

    def publish(self, run_id: str) -> None:
        for subscriber in list(self._subscribers.get(run_id, ())):
            try:
                subscriber.put_nowait(None)
            except asyncio.QueueFull:
                # One pending notification is sufficient: clients re-read by cursor.
                pass


_broker = RunEventBroker()


def get_event_broker() -> RunEventBroker:
    return _broker
