from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class RiskClass(StrEnum):
    READ_ONLY = "R0"
    REVERSIBLE_LOCAL = "R1"
    CONTROLLED_EXECUTION = "R2"
    PERSISTENT_EXTERNAL = "R3"
    PRIVILEGED = "R4"


class ApprovalMode(StrEnum):
    PLAN = "plan"
    CONFIRM_EACH = "confirm_each"
    ALLOW_WORKSPACE_EDITS = "allow_workspace_edits"
    SMART_DEVELOPMENT = "smart_development"
    ALL_APPROVALS_FOR_RUN = "all_approvals_for_run"


class PolicyAction(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: RiskClass
    workspace_scope: str = "/workspace"


class PolicyDecision(BaseModel):
    action: PolicyAction
    reason: str
    mode: ApprovalMode
    policy_version: str = "p0.1"
    hard_deny: bool = False


class ApprovalRequest(BaseModel):
    id: str
    run_id: str
    action_type: str
    scope: dict[str, Any]
    status: str
    requested_at: str
    decided_at: str | None = None
    expires_at: str | None = None


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    grant_scope: str = Field(default="once", pattern="^(once|run|workspace|all_approved_run)$")


class ToolCallRequest(BaseModel):
    tool: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_mode: ApprovalMode = ApprovalMode.CONFIRM_EACH


class ToolCallResponse(BaseModel):
    tool_call: ToolCall
    policy: PolicyDecision
    status: str
    result: Any | None = None
    approval: ApprovalRequest | None = None
