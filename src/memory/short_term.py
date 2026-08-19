from __future__ import annotations
import json
from src.config import get_settings

class ShortTermMemory:
    def __init__(self, redis_client=None):
        self.client = redis_client
        self.settings = get_settings()

    async def append(self, session_id: str, message: dict) -> None:
        if self.client is not None:
            await self.client.rpush(f"session:{session_id}:messages", json.dumps(message, ensure_ascii=False))
            await self.client.expire(f"session:{session_id}:messages", 86400)

    async def get(self, session_id: str, limit: int = 20) -> list[dict]:
        if self.client is None:
            return []
        values = await self.client.lrange(f"session:{session_id}:messages", -limit, -1)
        return [json.loads(item) for item in values]
