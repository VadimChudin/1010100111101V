from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .runtime import LocalRuntime


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


class LocalGraphitiMemory:
    """Local Graphiti adapter with cloud-safe provenance envelopes.

    A compatible graphiti-core client is optional. The event is durable even when
    the graph database or LLM provider is temporarily unavailable.
    """

    def __init__(self, runtime: LocalRuntime, graphiti_client: Any | None = None) -> None:
        self.runtime = runtime
        self.client = graphiti_client

    async def add_episode(
        self,
        name: str,
        content: str,
        *,
        source_run_id: str | None = None,
        source_commit_sha: str | None = None,
        source: str = "local_runtime",
    ) -> str:
        episode_id = f"episode-{uuid4()}"
        occurred_at = iso_now()
        envelope = {
            "episode_id": episode_id,
            "group_id": self.runtime.config.project_id,
            "name": name,
            "content": content,
            "source": source,
            "source_run_id": source_run_id,
            "source_commit_sha": source_commit_sha,
            "occurred_at": occurred_at,
        }
        if self.client is not None:
            await self.client.add_episode(
                name=name,
                episode_body=content,
                source_description=source,
                group_id=self.runtime.config.project_id,
            )
        self.runtime.enqueue(
            {
                "event_id": f"evt-{episode_id}",
                "type": "graphiti.episode",
                "entity_id": episode_id,
                "base_revision": 0,
                "payload": envelope,
                "occurred_at": occurred_at,
            }
        )
        return episode_id

    async def replay_cloud_event(self, event: dict[str, Any]) -> bool:
        if event.get("type") != "graphiti.episode" or self.client is None:
            return False
        envelope = dict(event.get("payload") or {})
        if envelope.get("group_id") != self.runtime.config.project_id:
            return False
        await self.client.add_episode(
            name=str(envelope["name"]),
            episode_body=str(envelope["content"]),
            source_description=str(envelope.get("source", "cloud_replay")),
            group_id=self.runtime.config.project_id,
        )
        return True
