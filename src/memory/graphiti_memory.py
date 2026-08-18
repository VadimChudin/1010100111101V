"""Long-term episodic memory backed by Graphiti and Neo4j.

The import and connection are lazy so tests and local API startup can work
when Graphiti is intentionally disabled.
"""
from typing import Any
from src.config import Settings, get_settings

class GraphitiMemory:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client: Any = None

    async def connect(self) -> None:
        if not self.settings.graphiti_enabled:
            return
        try:
            from graphiti_core import Graphiti  # type: ignore
            self.client = Graphiti(self.settings.neo4j_uri, self.settings.neo4j_username, self.settings.neo4j_password)
        except (ImportError, TypeError):
            self.client = None

    async def add_episode(self, name: str, content: str, source: str = "agent") -> bool:
        if self.client is None:
            return False
        try:
            await self.client.add_episode(name=name, episode_body=content, source_description=source)
            return True
        except Exception:
            return False

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if self.client is None:
            return []
        try:
            results = await self.client.search(query=query, num_results=limit)
            return [{"content": getattr(item, "fact", str(item))} for item in results]
        except Exception:
            return []

    async def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close:
            result = close()
            if hasattr(result, "__await__"):
                await result
        self.client = None
