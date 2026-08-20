from __future__ import annotations

import json
from typing import Any

import httpx

from .runtime import LocalRuntime, git_inventory
from .serena import validate_tool

MAX_RESULT_CHARS = 24_000
SERENA_ENDPOINT = "http://127.0.0.1:9121/mcp"


class LocalSerenaMcpClient:
    """Minimal local-only MCP client for the compiled Serena read-only allow-list."""

    def __init__(self, endpoint: str = SERENA_ENDPOINT, *, client: httpx.AsyncClient | None = None) -> None:
        if not endpoint.startswith("http://127.0.0.1:") and not endpoint.startswith("http://localhost:"):
            raise ValueError("Serena endpoint must be loopback-only")
        self.endpoint = endpoint
        self._client = client
        self._session_id: str | None = None
        self._request_id = 0

    async def _response_payload(self, response: httpx.Response, request_id: int) -> dict[str, Any]:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if not line.startswith("data:"):
                    continue
                candidate = json.loads(line.removeprefix("data:").strip())
                if candidate.get("id") == request_id:
                    return candidate
            raise RuntimeError("Serena MCP response did not include the expected JSON-RPC result")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Serena MCP response was not a JSON object")
        return payload

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        headers = {"Accept": "application/json, text/event-stream"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        if self._client is not None:
            response = await self._client.post(self.endpoint, headers=headers, json=body)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.endpoint, headers=headers, json=body)
        if session_id := response.headers.get("Mcp-Session-Id"):
            self._session_id = session_id
        payload = await self._response_payload(response, request_id)
        if "error" in payload:
            raise RuntimeError(f"Serena MCP error: {payload['error']}")
        return dict(payload.get("result") or {})

    async def initialize(self) -> None:
        await self._request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "agent-room-runtime", "version": "0.1.0"},
            },
        )
        headers = {"Accept": "application/json, text/event-stream"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        if self._client is not None:
            response = await self._client.post(self.endpoint, headers=headers, json=notification)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.endpoint, headers=headers, json=notification)
        if response.status_code not in {200, 202}:
            response.raise_for_status()

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        validate_tool(tool_name)
        await self.initialize()
        return await self._request("tools/call", {"name": tool_name, "arguments": arguments})


def _bounded(value: Any) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded) <= MAX_RESULT_CHARS:
        return value
    return {"truncated": True, "preview": encoded[:MAX_RESULT_CHARS], "total_characters": len(encoded)}


class DeviceJobExecutor:
    """Executes only fixed read-only semantic jobs delivered by a matching cloud lease."""

    def __init__(self, runtime: LocalRuntime, *, serena: LocalSerenaMcpClient | None = None, graphiti_client: Any | None = None) -> None:
        self.runtime = runtime
        self.serena = serena or LocalSerenaMcpClient()
        self.graphiti_client = graphiti_client

    async def execute(self, job: dict[str, Any]) -> dict[str, Any]:
        if job.get("project_id") != self.runtime.config.project_id or job.get("device_id") != self.runtime.config.device_id:
            raise PermissionError("Delivered job does not match this paired runtime")
        job_type = str(job.get("type", ""))
        payload = dict(job.get("payload") or {})
        if job_type == "find_symbol":
            result = await self.serena.call(
                "find_symbol",
                {key: payload[key] for key in ("name_path", "relative_path", "include_body") if key in payload},
            )
            return _bounded({"tool": "find_symbol", "response": result})
        if job_type == "find_references":
            result = await self.serena.call(
                "find_referencing_symbols",
                {key: payload[key] for key in ("name_path", "relative_path") if key in payload},
            )
            return _bounded({"tool": "find_referencing_symbols", "response": result})
        if job_type == "index_workspace":
            return _bounded({"inventory": git_inventory(self.runtime.config.workspace_root), "serena": "local semantic index is owned by the loopback Serena service"})
        if job_type == "retrieve_project_memory":
            return await self._retrieve_project_memory(payload)
        workspace_operations = {
            "refresh_workspace_index", "list_workspace_files", "search_workspace_text", "read_file_range", "apply_unified_patch",
            "run_test_profile", "git_status", "git_diff", "git_commit", "git_push",
        }
        if job_type in workspace_operations:
            if not self.runtime.config.workspace_id or payload.get("workspace_id") != self.runtime.config.workspace_id:
                raise PermissionError("Workspace job does not match this registered local workspace")
            from .workspace_ops import LocalWorkspaceExecutor

            workspace = LocalWorkspaceExecutor(self.runtime.config.workspace_root)
            if job_type == "refresh_workspace_index":
                return _bounded(workspace.refresh_index())
            if job_type == "list_workspace_files":
                return _bounded(workspace.list_files(str(payload.get("prefix", "")), int(payload.get("limit", 500))))
            if job_type == "search_workspace_text":
                return _bounded(workspace.search_text(str(payload["query"]), str(payload.get("prefix", "")), int(payload.get("limit", 50))))
            if job_type == "read_file_range":
                return _bounded(workspace.read_file_range(str(payload["relative_path"]), int(payload["start_line"]), int(payload["end_line"])))
            if job_type == "apply_unified_patch":
                return _bounded(workspace.apply_unified_patch(str(payload["patch"])))
            if job_type == "run_test_profile":
                return _bounded(workspace.run_test_profile(str(payload["profile"])))
            if job_type == "git_status":
                return _bounded(workspace.git_status())
            if job_type == "git_diff":
                return _bounded(workspace.git_diff(payload.get("relative_path")))
            if job_type == "git_commit":
                return _bounded(workspace.git_commit(str(payload["message"])))
            if job_type == "git_push":
                return _bounded(workspace.git_push(str(payload.get("remote", "origin")), payload.get("branch")))
        raise PermissionError("Job type is outside the compiled local allow-list")

    async def _retrieve_project_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query", "")).strip()
        limit = int(payload.get("limit", 8))
        if not query or not 1 <= limit <= 20:
            raise ValueError("retrieve_project_memory request is invalid")
        if self.graphiti_client is not None:
            search = getattr(self.graphiti_client, "search", None)
            if not callable(search):
                raise RuntimeError("Configured Graphiti client does not support retrieval")
            records = await search(query, group_ids=[self.runtime.config.project_id], num_results=limit)
            return _bounded({"query": query, "records": records})
        # Fallback is deliberately limited to provenance envelopes already synchronized to this paired runtime.
        matches: list[dict[str, Any]] = []
        lowered = query.lower()
        for event in reversed(self.runtime.outbox.received()):
            if event.get("type") != "graphiti.episode":
                continue
            envelope = dict(event.get("payload") or {})
            if envelope.get("group_id") != self.runtime.config.project_id:
                continue
            text = f"{envelope.get('name', '')}\n{envelope.get('content', '')}".lower()
            if lowered in text:
                matches.append({key: envelope.get(key) for key in ("episode_id", "name", "content", "source", "occurred_at")})
            if len(matches) >= limit:
                break
        return _bounded({"query": query, "records": matches, "source": "local provenance envelope fallback"})
