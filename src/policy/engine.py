from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

from .models import ApprovalMode, PolicyAction, PolicyDecision, RiskClass, ToolCall


_SECRET_PATTERNS = (".env", ".env.*", "**/.env", "**/.env.*", "*.pem", "*.key", "id_rsa", "**/id_rsa", "secrets/**", "**/secrets/**")
_HARD_DENY_TOOLS = {"raw_shell", "execute_shell", "deploy", "read_secret", "write_env", "install_package"}


class PolicyEngine:
    """Deterministic policy gate; an LLM cannot bypass this layer."""

    version = "p0.1"

    def _paths(self, arguments: dict[str, Any]) -> Iterable[str]:
        for key in ("path", "paths", "relative_path", "from_path", "to_path"):
            value = arguments.get(key)
            if isinstance(value, str):
                yield value.lstrip("/")
            elif isinstance(value, list):
                yield from (str(item).lstrip("/") for item in value)

    def _is_secret_path(self, path: str) -> bool:
        normalized = PurePosixPath(path).as_posix()
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in _SECRET_PATTERNS)

    def _hard_deny_reason(self, call: ToolCall) -> str | None:
        if call.tool in _HARD_DENY_TOOLS:
            return f"{call.tool} is outside the P0 typed-tool allowlist."
        if any(self._is_secret_path(path) for path in self._paths(call.arguments)):
            return "Secret, credential, and .env paths are never exposed to agent tools."
        if call.risk == RiskClass.PRIVILEGED:
            return "Privileged R4 actions require an isolated runner and are not available in P0."
        return None

    def decide(
        self,
        call: ToolCall,
        mode: ApprovalMode,
        grants: set[str] | None = None,
        denied_tools: set[str] | None = None,
    ) -> PolicyDecision:
        hard_deny = self._hard_deny_reason(call)
        if hard_deny:
            return PolicyDecision(action=PolicyAction.DENY, reason=hard_deny, mode=mode, hard_deny=True, policy_version=self.version)

        if call.tool in (denied_tools or set()):
            return PolicyDecision(action=PolicyAction.DENY, reason="A run-scoped deny rule matches this tool.", mode=mode, policy_version=self.version)

        active_grants = grants or set()
        if call.id in active_grants or call.tool in active_grants or "all_approved_run" in active_grants:
            return PolicyDecision(action=PolicyAction.ALLOW, reason="A scoped approval grant permits this action.", mode=mode, policy_version=self.version)

        if call.risk == RiskClass.READ_ONLY:
            return PolicyDecision(action=PolicyAction.ALLOW, reason="Read-only tool inside the workspace scope.", mode=mode, policy_version=self.version)

        if mode == ApprovalMode.PLAN:
            return PolicyDecision(action=PolicyAction.ASK, reason="Plan mode only auto-allows read-only inspection.", mode=mode, policy_version=self.version)

        if mode == ApprovalMode.CONFIRM_EACH:
            return PolicyDecision(action=PolicyAction.ASK, reason="Confirm-each mode requires a specific approval.", mode=mode, policy_version=self.version)

        if mode == ApprovalMode.ALLOW_WORKSPACE_EDITS and call.risk == RiskClass.REVERSIBLE_LOCAL:
            return PolicyDecision(action=PolicyAction.ALLOW, reason="Workspace-edit mode permits reversible local edits.", mode=mode, policy_version=self.version)

        if mode in {ApprovalMode.SMART_DEVELOPMENT, ApprovalMode.ALL_APPROVALS_FOR_RUN} and call.risk in {
            RiskClass.REVERSIBLE_LOCAL,
            RiskClass.CONTROLLED_EXECUTION,
        }:
            return PolicyDecision(action=PolicyAction.ALLOW, reason="The selected sandboxed mode permits this bounded local action.", mode=mode, policy_version=self.version)

        return PolicyDecision(action=PolicyAction.ASK, reason="No allow rule matches; explicit approval is required.", mode=mode, policy_version=self.version)
