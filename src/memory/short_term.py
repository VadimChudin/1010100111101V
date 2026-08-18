"""Redis-backed short-term conversation memory."""
import json
from typing import Any
from redis.asyncio import Redis
from src.config import Settings, get_settings

class ShortTermMemory:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.redis: Redis = Redis.from_url(self.settings.redis_url, decode_responses=True)

    def _key(self, thread_id: str) -> str:
        return f"agent:thread:{thread_id}"

    async def append(self, thread_id: str, event: dict[str, Any]) -> None:
        await self.redis.rpush(self._key(thread_id), json.dumps(event, ensure_ascii=False))
        await self.redis.expire(self._key(thread_id), self.settings.redis_ttl_seconds)

    async def get(self, thread_id: str) -> list[dict[str, Any]]:
        values = await self.redis.lrange(self._key(thread_id), 0, -1)
        return [json.loads(value) for value in values]

    async def close(self) -> None:
        await self.redis.aclose()
