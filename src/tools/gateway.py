from __future__ import annotations

import asyncio
import fnmatch
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.config import get_settings
from src.events import get_event_broker
from src.policy import ApprovalMode, ApprovalRequest, PolicyAction, PolicyEngine, RiskClass, ToolCall, ToolCallRequest, ToolCallResponse
from src.storage import PersistedApproval, SQLiteRunStore

from .files import safe_path


_SECRET_PATTERNS = (".env", ".env.*", "**/.env", "**/.env.*", "*.pem", "*.key", "id_rsa", "**/id_rsa", "secrets/**", "**/secrets/**")


def _is_secret_path(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in _SECRET_PATTERNS)


def _relative_workspace_path(path: Path) -> str:
    root = Path(get_settings().workspace_root).resolve()
    return path.resolve().relative_to(root).as_posix()


async def list_files(arguments: dict[str, Any]) -> dict[str, Any]:
    relative = str(arguments.get("path", "."))
    recursive = bool(arguments.get("recursive", False))
    limit = min(max(int(arguments.get("limit", 100)), 1), 500)
    target = safe_path(relative)
    if not target.exists():
        raise FileNotFoundError(relative)
    candidates = target.rglob("*") if recursive else target.iterdir()
    entries: list[dict[str, str]] = []
    for item in candidates:
        safe_relative = _relative_workspace_path(item)
        if _is_secret_path(safe_relative):
            continue
        entries.append({"path": safe_relative, "kind": "directory" if item.is_dir() else "file"})
        if len(entries) >= limit:
            break
    return {"entries": entries, "truncated": len(entries) >= limit}


async def read_workspace_file(arguments: dict[str, Any]) -> dict[str, Any]:
    relative = str(arguments["path"])
    target = safe_path(relative)
    if not target.is_file():
        raise FileNotFoundError(relative)
    if _is_secret_path(_relative_workspace_path(target)):
        raise PermissionError("Secret path access is denied.")
    max_chars = min(max(int(arguments.get("max_chars", get_settings().max_tool_output_chars)), 1), get_settings().max_tool_output_chars)
    content = await asyncio.to_thread(target.read_text, encoding="utf-8", errors="replace")
    return {"path": _relative_workspace_path(target), "content": content[:max_chars], "truncated": len(content) > max_chars}


async def search_workspace_text(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments["query"])
    if not query or len(query) > 200:
        raise ValueError("query must contain 1-200 characters")
    relative = str(arguments.get("path", "."))
    limit = min(max(int(arguments.get("limit", 50)), 1), 200)
    root = safe_path(relative)
    if not root.exists():
        raise FileNotFoundError(relative)
    results: list[dict[str, Any]] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file() or file_path.stat().st_size > 1_000_000:
            continue
        safe_relative = _relative_workspace_path(file_path)
        if _is_secret_path(safe_relative):
            continue
        try:
            lines = await asyncio.to_thread(file_path.read_text, encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_number, line in enumerate(lines.splitlines(), start=1):
            if query.casefold() in line.casefold():
                results.append({"path": safe_relative, "line": line_number, "content": line[:500]})
                if len(results) >= limit:
                    return {"matches": results, "truncated": True}
    return {"matches": results, "truncated": False}


async def create_workspace_file(arguments: dict[str, Any]) -> dict[str, Any]:
    relative = str(arguments["path"])
    content = arguments.get("content")
    if not isinstance(content, str) or len(content) > 200_000:
        raise ValueError("content must be a string no longer than 200000 characters")
    target = safe_path(relative)
    if _is_secret_path(_relative_workspace_path(target)):
        raise PermissionError("Secret path access is denied.")
    if target.exists():
        raise FileExistsError(relative)
    await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(target.write_text, content, encoding="utf-8")
    return {"path": _relative_workspace_path(target), "created": True, "bytes_written": len(content.encode("utf-8"))}


async def replace_workspace_text(arguments: dict[str, Any]) -> dict[str, Any]:
    relative = str(arguments["path"])
    expected = arguments.get("expected")
    replacement = arguments.get("replacement")
    if not isinstance(expected, str) or not isinstance(replacement, str) or not expected:
        raise ValueError("expected and replacement must be non-empty strings")
    target = safe_path(relative)
    if not target.is_file():
        raise FileNotFoundError(relative)
    if _is_secret_path(_relative_workspace_path(target)):
        raise PermissionError("Secret path access is denied.")
    original = await asyncio.to_thread(target.read_text, encoding="utf-8", errors="replace")
    occurrences = original.count(expected)
    if occurrences != 1:
        raise ValueError("expected must match exactly one location")
    updated = original.replace(expected, replacement, 1)
    await asyncio.to_thread(target.write_text, updated, encoding="utf-8")
    return {"path": _relative_workspace_path(target), "replaced": True, "bytes_delta": len(updated.encode("utf-8")) - len(original.encode("utf-8"))}


async def _git(arguments: list[str]) -> dict[str, Any]:
    root = Path(get_settings().workspace_root).resolve()

    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *arguments], cwd=root, capture_output=True, text=True, timeout=10, check=False)

    result = await asyncio.to_thread(run)
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return {"output": result.stdout[:get_settings().max_tool_output_chars], "exit_code": result.returncode}


async def git_status(_: dict[str, Any]) -> dict[str, Any]:
    return await _git(["status", "--short"])


async def git_diff(arguments: dict[str, Any]) -> dict[str, Any]:
    target = str(arguments.get("path", ""))
    if target and _is_secret_path(target):
        raise PermissionError("Secret path access is denied.")
    command = ["diff", "--no-ext-diff", "--"] + ([target] if target else [])
    return await _git(command)


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    risk: RiskClass
    handler: ToolHandler


TOOL_CATALOG: dict[str, ToolSpec] = {
    "list_files": ToolSpec("list_files", RiskClass.READ_ONLY, list_files),
    "read_file": ToolSpec("read_file", RiskClass.READ_ONLY, read_workspace_file),
    "search_text": ToolSpec("search_text", RiskClass.READ_ONLY, search_workspace_text),
    "git_status": ToolSpec("git_status", RiskClass.READ_ONLY, git_status),
    "git_diff": ToolSpec("git_diff", RiskClass.READ_ONLY, git_diff),
    "create_file": ToolSpec("create_file", RiskClass.REVERSIBLE_LOCAL, create_workspace_file),
    "replace_text": ToolSpec("replace_text", RiskClass.REVERSIBLE_LOCAL, replace_workspace_text),
}


class ToolGateway:
    """Policy-gated tool catalog. Raw command strings never reach this boundary."""

    def __init__(self, store: SQLiteRunStore, policy: PolicyEngine | None = None) -> None:
        self.store = store
        self.policy = policy or PolicyEngine()
        self.catalog = TOOL_CATALOG

    async def _emit(self, run_id: str, event: dict[str, Any]) -> None:
        await self.store.append_events(run_id, [event])
        get_event_broker().publish(run_id)

    def _call_from_request(self, request: ToolCallRequest) -> ToolCall:
        spec = self.catalog.get(request.tool)
        if spec is None:
            # The unknown tool remains a denied ToolCall so the policy decision
            # is auditable without ever invoking an unregistered provider.
            return ToolCall(tool=request.tool, arguments=request.arguments, risk=RiskClass.PRIVILEGED)
        return ToolCall(tool=spec.name, arguments=request.arguments, risk=spec.risk)

    @staticmethod
    def _approval_model(approval: PersistedApproval) -> ApprovalRequest:
        return ApprovalRequest(
            id=approval.id,
            run_id=approval.run_id,
            action_type=approval.action_type,
            scope=approval.scope,
            status=approval.status,
            requested_at=approval.requested_at,
            decided_at=approval.decided_at,
            expires_at=approval.expires_at,
        )

    async def invoke(self, run_id: str, request: ToolCallRequest) -> ToolCallResponse:
        call = self._call_from_request(request)
        grants = await self.store.approval_grants(run_id)
        decision = self.policy.decide(call, request.approval_mode, grants=grants)
        await self._emit(
            run_id,
            {"type": "policy.decided", "payload": {"tool_call_id": call.id, "tool": call.tool, **decision.model_dump()}},
        )

        if decision.action == PolicyAction.DENY:
            return ToolCallResponse(tool_call=call, policy=decision, status="denied")

        if decision.action == PolicyAction.ASK:
            approval = await self.store.create_approval(
                str(uuid4()),
                run_id,
                call.tool,
                {"tool_call": call.model_dump(mode="json"), "tool": call.tool, "arguments": call.arguments, "mode": request.approval_mode},
            )
            await self._emit(
                run_id,
                {"type": "approval.requested", "payload": {"approval_id": approval.id, "tool_call_id": call.id, "tool": call.tool, "risk": call.risk}},
            )
            return ToolCallResponse(tool_call=call, policy=decision, status="awaiting_approval", approval=self._approval_model(approval))

        return await self._execute(run_id, call, decision)

    async def _execute(self, run_id: str, call: ToolCall, decision) -> ToolCallResponse:
        spec = self.catalog.get(call.tool)
        if spec is None:
            denied = self.policy.decide(call, decision.mode)
            return ToolCallResponse(tool_call=call, policy=denied, status="denied")
        await self._emit(run_id, {"type": "tool.started", "payload": {"tool_call_id": call.id, "tool": call.tool}})
        try:
            result = await spec.handler(call.arguments)
        except Exception as exc:
            await self._emit(run_id, {"type": "tool.failed", "payload": {"tool_call_id": call.id, "tool": call.tool, "message": str(exc)}})
            return ToolCallResponse(tool_call=call, policy=decision, status="failed")
        await self._emit(run_id, {"type": "tool.completed", "payload": {"tool_call_id": call.id, "tool": call.tool, "result": result}})
        return ToolCallResponse(tool_call=call, policy=decision, status="completed", result=result)

    async def resolve(self, approval_id: str, approved: bool, grant_scope: str) -> ToolCallResponse | None:
        approval = await self.store.resolve_approval(approval_id, approved, grant_scope)
        if approval is None:
            return None
        call = ToolCall.model_validate(approval.scope["tool_call"])
        decision = self.policy.decide(call, ApprovalMode.CONFIRM_EACH)
        event_type = "approval.granted" if approved else "approval.denied"
        await self._emit(approval.run_id, {"type": event_type, "payload": {"approval_id": approval.id, "tool_call_id": call.id, "grant_scope": grant_scope}})
        if not approved:
            return ToolCallResponse(tool_call=call, policy=decision, status="denied", approval=self._approval_model(approval))
        # This exact immutable tool call was authorised. Future calls still go
        # through policy and can use only stored run/workspace grants.
        approved_decision = decision.model_copy(update={"action": PolicyAction.ALLOW, "reason": "The immutable approval request was granted."})
        response = await self._execute(approval.run_id, call, approved_decision)
        return response.model_copy(update={"approval": self._approval_model(approval)})
