from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


SerenaTransport = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class SerenaClient:
    """Typed read-only Serena provider boundary.

    A runtime-specific MCP transport is injected only after the Serena connector
    is enabled for a deployment. The API code never spawns an MCP CLI process or
    exposes Serena's editing operations through the public tool catalog.
    """

    def __init__(self, transport: SerenaTransport | None = None):
        self._transport = transport

    @property
    def available(self) -> bool:
        return self._transport is not None

    async def _call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._transport is None:
            return {"ok": False, "reason": "Serena read-only provider is not enabled for this deployment."}
        return await self._transport(tool, arguments)

    async def outline(self, relative_path: str) -> dict[str, Any]:
        return await self._call("get_symbols_overview", {"relative_path": relative_path})

    async def find_symbol(self, symbol: str, path: str | None = None, include_body: bool = False) -> dict[str, Any]:
        arguments: dict[str, Any] = {"name_path": symbol, "include_body": include_body}
        if path:
            arguments["relative_path"] = path
        return await self._call("find_symbol", arguments)

    async def references(self, symbol: str, path: str | None = None) -> dict[str, Any]:
        arguments: dict[str, Any] = {"name_path": symbol}
        if path:
            arguments["relative_path"] = path
        return await self._call("find_referencing_symbols", arguments)
