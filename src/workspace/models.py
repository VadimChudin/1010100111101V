from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class MarkerType(StrEnum):
    NOTE = "note"
    TASK = "task"
    DECISION = "decision"
    QUESTION = "question"
    ERROR = "error"
    BLOCKED = "blocked"
    RUNNING = "running"
    APPROVAL_REQUIRED = "approval_required"


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class WorkspaceProject(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    updated_at: str


class ModuleCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    kind: str = Field(default="component", max_length=50)
    source_scope: str = Field(default="", max_length=500)
    aliases: list[str] = Field(default_factory=list, max_length=25)
    dependencies: list[str] = Field(default_factory=list, max_length=50)
    position_x: float = 0
    position_y: float = 0
    status: str = Field(default="active", max_length=50)


class WorkspaceModule(ModuleCreateRequest):
    id: str
    project_id: str
    created_at: str
    updated_at: str


class NoteCreateRequest(BaseModel):
    module_id: str
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=12000)
    kind: MarkerType = MarkerType.NOTE
    source_run_id: str | None = None


class WorkspaceNote(NoteCreateRequest):
    id: str
    project_id: str
    author: str
    created_at: str


class TaskCreateRequest(BaseModel):
    module_id: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=12000)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=50)
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    source_run_id: str | None = None


class TaskStatusRequest(BaseModel):
    status: TaskStatus


class WorkspaceTask(TaskCreateRequest):
    id: str
    project_id: str
    status: TaskStatus
    created_at: str
    updated_at: str


class WorkspaceMarker(BaseModel):
    id: str
    project_id: str
    module_id: str
    type: MarkerType
    title: str
    state: str
    source_kind: str
    source_id: str
    created_at: str


class WorkspaceSnapshot(BaseModel):
    project: WorkspaceProject
    modules: list[WorkspaceModule]
    notes: list[WorkspaceNote]
    tasks: list[WorkspaceTask]
    markers: list[WorkspaceMarker]


def new_id() -> str:
    return str(uuid4())


def json_object(value: dict[str, Any] | None = None) -> dict[str, Any]:
    return value or {}
