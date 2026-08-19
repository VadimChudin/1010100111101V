from __future__ import annotations

class SerenaClient:
    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint

    async def find_symbol(self, symbol: str, path: str | None = None) -> dict:
        return {"ok": False, "symbol": symbol, "path": path, "reason": "Serena MCP endpoint is not configured"}

    async def references(self, symbol: str) -> dict:
        return {"ok": False, "symbol": symbol, "reason": "Serena MCP endpoint is not configured"}
