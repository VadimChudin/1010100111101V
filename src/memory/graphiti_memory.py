from __future__ import annotations
from src.config import get_settings

class GraphitiMemory:
    """Thin adapter; production wiring should initialize graphiti-core with Neo4j."""
    def __init__(self, graphiti_client=None):
        self.client = graphiti_client
        self.settings = get_settings()

    async def add_episode(self, session_id: str, content: str, source: str = "agent") -> dict:
        if self.client is None:
            return {"stored": False, "reason": "Graphiti client not configured"}
        # Keep the adapter version-agnostic: Graphiti APIs evolve; inject a compatible client.
        result = await self.client.add_episode(name=f"session-{session_id}", episode_body=content, source_description=source)
        return {"stored": True, "result": result}

    async def search(self, query: str, user_id: str, limit: int = 5) -> list[dict]:
        if self.client is None:
            return []
        results = await self.client.search(query=query, group_id=user_id, num_results=limit)
        return list(results)
