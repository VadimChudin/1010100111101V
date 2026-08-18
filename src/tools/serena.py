"""Serena MCP/LSP integration placeholder."""
import httpx
from src.config import Settings, get_settings

class SerenaClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def call(self, method: str, params: dict) -> dict:
        if not self.settings.serena_enabled:
            return {"ok": False, "message": "Serena integration is disabled"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.settings.serena_mcp_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            response.raise_for_status()
            return response.json()
