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


class DeviceStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    REVOKED = "revoked"


class ProjectRuntimeMode(StrEnum):
    CLOUD = "cloud"
    LOCAL = "local"
    HYBRID = "hybrid"


class ProjectEventType(StrEnum):
    NOTE_CREATED = "note.created"
    TASK_CREATED = "task.created"
    TASK_STATUS_CHANGED = "task.status_changed"
    MARKER_CREATED = "marker.created"
    GRAPHITI_EPISODE = "graphiti.episode"


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
    origin: str = "manual"
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


class RepositoryFile(BaseModel):
    path: str = Field(min_length=1, max_length=1200)
    kind: str = Field(pattern="^(file|directory)$")
    language: str | None = Field(default=None, max_length=50)
    size: int | None = Field(default=None, ge=0)


class RepositoryDependency(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    ecosystem: str = Field(pattern="^(python|node)$")
    version: str = Field(default="", max_length=240)
    group: str = Field(default="production", max_length=80)


class RepositoryIndex(BaseModel):
    project_id: str
    repository_url: str
    branch: str
    commit_sha: str
    indexed_at: str
    files_count: int = Field(ge=0)
    modules_count: int = Field(ge=0)
    dependencies: list[RepositoryDependency] = Field(default_factory=list)


class WorkspaceSnapshot(BaseModel):
    project: WorkspaceProject
    modules: list[WorkspaceModule]
    notes: list[WorkspaceNote]
    tasks: list[WorkspaceTask]
    markers: list[WorkspaceMarker]


class LocalRepositoryInventory(BaseModel):
    repository_url: str = Field(default="local", max_length=2000)
    branch: str = Field(default="HEAD", max_length=240)
    commit_sha: str = Field(default="", max_length=80)
    dirty: bool = False
    tracked_files: int = Field(default=0, ge=0)
    workspace_fingerprint: str = Field(default="", max_length=128)


class DevicePairingRequest(BaseModel):
    name_hint: str = Field(default="Local runtime", min_length=1, max_length=160)
    expires_in_seconds: int = Field(default=600, ge=60, le=3600)


class DevicePairing(BaseModel):
    id: str
    project_id: str
    name_hint: str
    pairing_token: str
    expires_at: str


class DeviceRegistrationRequest(BaseModel):
    pairing_token: str = Field(min_length=24, max_length=512)
    name: str = Field(min_length=1, max_length=160)
    runtime_version: str = Field(default="0.1.0", min_length=1, max_length=80)
    public_key: str = Field(min_length=16, max_length=4096)
    capabilities: list[str] = Field(default_factory=list, max_length=25)
    inventory: LocalRepositoryInventory | None = None


class ProjectDevice(BaseModel):
    id: str
    project_id: str
    owner_user_id: str
    name: str
    status: DeviceStatus
    runtime_version: str
    capabilities: list[str] = Field(default_factory=list)
    inventory: LocalRepositoryInventory | None = None
    last_seen_at: str | None = None
    last_synced_at: str | None = None
    created_at: str
    revoked_at: str | None = None


class DeviceRegistration(ProjectDevice):
    device_token: str


class ProjectEventMutation(BaseModel):
    event_id: str = Field(min_length=8, max_length=120)
    type: ProjectEventType
    entity_id: str = Field(min_length=1, max_length=120)
    base_revision: int = Field(default=0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str = Field(min_length=10, max_length=64)


class ProjectEvent(BaseModel):
    sequence: int = Field(ge=1)
    project_id: str
    event_id: str
    device_id: str | None = None
    actor_id: str | None = None
    type: ProjectEventType
    entity_id: str
    base_revision: int = Field(ge=0)
    entity_revision: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str
    created_at: str


class SyncConflict(BaseModel):
    event_id: str
    code: str
    detail: str
    entity_id: str | None = None
    current_revision: int | None = None


class DeviceSyncRequest(BaseModel):
    cursor: int = Field(default=0, ge=0)
    events: list[ProjectEventMutation] = Field(default_factory=list, max_length=100)
    inventory: LocalRepositoryInventory | None = None


class DeviceSyncResponse(BaseModel):
    accepted_event_ids: list[str] = Field(default_factory=list)
    conflicts: list[SyncConflict] = Field(default_factory=list)
    events: list[ProjectEvent] = Field(default_factory=list)
    server_cursor: int = Field(ge=0)
    device: ProjectDevice


class GraphitiEpisodeEnvelope(BaseModel):
    episode_id: str = Field(min_length=8, max_length=120)
    group_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=24000)
    source: str = Field(default="local_runtime", max_length=80)
    source_run_id: str | None = Field(default=None, max_length=120)
    source_commit_sha: str | None = Field(default=None, max_length=80)
    occurred_at: str = Field(min_length=10, max_length=64)


def new_id() -> str:
    return str(uuid4())


def json_object(value: dict[str, Any] | None = None) -> dict[str, Any]:
    return value or {}
