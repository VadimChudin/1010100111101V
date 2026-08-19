from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.storage import SQLiteRunStore

from .models import (
    MarkerType,
    ModuleCreateRequest,
    NoteCreateRequest,
    ProjectCreateRequest,
    TaskCreateRequest,
    TaskStatus,
    WorkspaceMarker,
    WorkspaceModule,
    WorkspaceNote,
    WorkspaceProject,
    WorkspaceSnapshot,
    WorkspaceTask,
    new_id,
)


WORKSPACE_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS modules (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_scope TEXT NOT NULL DEFAULT '',
    aliases_json TEXT NOT NULL DEFAULT '[]',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    position_x REAL NOT NULL DEFAULT 0,
    position_y REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    kind TEXT NOT NULL,
    author TEXT NOT NULL,
    source_run_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    source_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS module_markers (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open',
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_modules_project ON modules(project_id);
CREATE INDEX IF NOT EXISTS idx_notes_project_module ON notes(project_id, module_id);
CREATE INDEX IF NOT EXISTS idx_workspace_tasks_project_module ON workspace_tasks(project_id, module_id);
CREATE INDEX IF NOT EXISTS idx_markers_project_module ON module_markers(project_id, module_id);
"""


DEFAULT_MODULES = (
    {"title": "Agent Orchestrator", "kind": "backend", "source_scope": "src/orchestrator", "aliases": ["agent", "graph", "orchestrator"], "position_x": 80, "position_y": 120},
    {"title": "Chat & Timeline", "kind": "frontend", "source_scope": "frontend/client/src/hooks/useChat.ts", "aliases": ["chat", "timeline", "conversation"], "position_x": 390, "position_y": 80},
    {"title": "Durable State", "kind": "backend", "source_scope": "src/storage/run_store.py", "aliases": ["storage", "runs", "sqlite"], "position_x": 400, "position_y": 300},
    {"title": "Policy Gateway", "kind": "backend", "source_scope": "src/policy", "aliases": ["approvals", "tools", "permissions"], "position_x": 720, "position_y": 180},
    {"title": "Workspace Canvas", "kind": "frontend", "source_scope": "frontend/client/src/components/TaskGraph.tsx", "aliases": ["workspace", "canvas", "modules"], "position_x": 720, "position_y": 420},
)


def now() -> str:
    return datetime.now(UTC).isoformat()


class WorkspaceStore:
    """Project memory repository sharing the durable SQLite WAL database."""

    def __init__(self, run_store: SQLiteRunStore) -> None:
        self.run_store = run_store
        self.database_path = Path(run_store.database_path)
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    async def initialize(self) -> None:
        if self._initialized:
            return
        await self.run_store.initialize()

        def create_schema() -> None:
            with self._connect() as connection:
                connection.executescript(WORKSPACE_SCHEMA)

        await asyncio.to_thread(create_schema)
        self._initialized = True

    @staticmethod
    def _project(row: sqlite3.Row) -> WorkspaceProject:
        return WorkspaceProject(id=row["id"], name=row["name"], description=row["description"], created_at=row["created_at"], updated_at=row["updated_at"])

    @staticmethod
    def _module(row: sqlite3.Row) -> WorkspaceModule:
        return WorkspaceModule(
            id=row["id"], project_id=row["project_id"], title=row["title"], kind=row["kind"], source_scope=row["source_scope"],
            aliases=json.loads(row["aliases_json"]), dependencies=json.loads(row["dependencies_json"]), position_x=row["position_x"], position_y=row["position_y"],
            status=row["status"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _note(row: sqlite3.Row) -> WorkspaceNote:
        return WorkspaceNote(
            id=row["id"], project_id=row["project_id"], module_id=row["module_id"], title=row["title"], content=row["content"], kind=row["kind"],
            author=row["author"], source_run_id=row["source_run_id"], created_at=row["created_at"],
        )

    @staticmethod
    def _task(row: sqlite3.Row) -> WorkspaceTask:
        return WorkspaceTask(
            id=row["id"], project_id=row["project_id"], module_id=row["module_id"], title=row["title"], description=row["description"],
            acceptance_criteria=json.loads(row["acceptance_criteria_json"]), status=row["status"], priority=row["priority"], source_run_id=row["source_run_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _marker(row: sqlite3.Row) -> WorkspaceMarker:
        return WorkspaceMarker(
            id=row["id"], project_id=row["project_id"], module_id=row["module_id"], type=row["type"], title=row["title"], state=row["state"],
            source_kind=row["source_kind"], source_id=row["source_id"], created_at=row["created_at"],
        )

    def _create_project_sync(self, project_id: str, request: ProjectCreateRequest) -> WorkspaceProject:
        timestamp = now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (project_id, request.name, request.description, timestamp, timestamp),
            )
        return WorkspaceProject(id=project_id, name=request.name, description=request.description, created_at=timestamp, updated_at=timestamp)

    async def create_project(self, request: ProjectCreateRequest) -> WorkspaceProject:
        await self.initialize()
        return await asyncio.to_thread(self._create_project_sync, new_id(), request)

    def _list_projects_sync(self) -> list[WorkspaceProject]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
        return [self._project(row) for row in rows]

    async def list_projects(self) -> list[WorkspaceProject]:
        await self.initialize()
        return await asyncio.to_thread(self._list_projects_sync)

    async def ensure_default_project(self) -> WorkspaceProject:
        await self.initialize()

        def create_default() -> WorkspaceProject:
            with self._connect() as connection:
                existing = connection.execute("SELECT * FROM projects WHERE id = 'default'").fetchone()
                if existing:
                    return self._project(existing)
                timestamp = now()
                connection.execute(
                    "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    ("default", "AI Agent Platform", "Default product workspace for the agent platform.", timestamp, timestamp),
                )
                for item in DEFAULT_MODULES:
                    connection.execute(
                        "INSERT INTO modules (id, project_id, title, kind, source_scope, aliases_json, dependencies_json, position_x, position_y, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (new_id(), "default", item["title"], item["kind"], item["source_scope"], json.dumps(item["aliases"]), "[]", item["position_x"], item["position_y"], "active", timestamp, timestamp),
                    )
                return WorkspaceProject(id="default", name="AI Agent Platform", description="Default product workspace for the agent platform.", created_at=timestamp, updated_at=timestamp)

        return await asyncio.to_thread(create_default)

    def _get_project_sync(self, project_id: str) -> WorkspaceProject | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._project(row) if row else None

    async def get_project(self, project_id: str) -> WorkspaceProject | None:
        await self.initialize()
        return await asyncio.to_thread(self._get_project_sync, project_id)

    def _create_module_sync(self, project_id: str, module_id: str, request: ModuleCreateRequest) -> WorkspaceModule:
        timestamp = now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO modules (id, project_id, title, kind, source_scope, aliases_json, dependencies_json, position_x, position_y, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (module_id, project_id, request.title, request.kind, request.source_scope, json.dumps(request.aliases), json.dumps(request.dependencies), request.position_x, request.position_y, request.status, timestamp, timestamp),
            )
        return WorkspaceModule(id=module_id, project_id=project_id, created_at=timestamp, updated_at=timestamp, **request.model_dump())

    async def create_module(self, project_id: str, request: ModuleCreateRequest) -> WorkspaceModule:
        await self.initialize()
        return await asyncio.to_thread(self._create_module_sync, project_id, new_id(), request)

    def _module_belongs_to_project(self, connection: sqlite3.Connection, project_id: str, module_id: str) -> bool:
        return connection.execute("SELECT 1 FROM modules WHERE id = ? AND project_id = ?", (module_id, project_id)).fetchone() is not None

    def _create_note_sync(self, project_id: str, note_id: str, request: NoteCreateRequest, author: str) -> WorkspaceNote:
        timestamp = now()
        with self._connect() as connection:
            if not self._module_belongs_to_project(connection, project_id, request.module_id):
                raise LookupError("Module not found in project")
            connection.execute(
                "INSERT INTO notes (id, project_id, module_id, title, content, kind, author, source_run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (note_id, project_id, request.module_id, request.title, request.content, request.kind, author, request.source_run_id, timestamp),
            )
            connection.execute(
                "INSERT INTO module_markers (id, project_id, module_id, type, title, state, source_kind, source_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), project_id, request.module_id, request.kind, request.title, "open", "note", note_id, timestamp),
            )
        return WorkspaceNote(id=note_id, project_id=project_id, author=author, created_at=timestamp, **request.model_dump())

    async def create_note(self, project_id: str, request: NoteCreateRequest, author: str = "operator") -> WorkspaceNote:
        await self.initialize()
        return await asyncio.to_thread(self._create_note_sync, project_id, new_id(), request, author)

    def _create_task_sync(self, project_id: str, task_id: str, request: TaskCreateRequest) -> WorkspaceTask:
        timestamp = now()
        with self._connect() as connection:
            if not self._module_belongs_to_project(connection, project_id, request.module_id):
                raise LookupError("Module not found in project")
            connection.execute(
                "INSERT INTO workspace_tasks (id, project_id, module_id, title, description, acceptance_criteria_json, status, priority, source_run_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, project_id, request.module_id, request.title, request.description, json.dumps(request.acceptance_criteria), TaskStatus.TODO, request.priority, request.source_run_id, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO module_markers (id, project_id, module_id, type, title, state, source_kind, source_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), project_id, request.module_id, MarkerType.TASK, request.title, "open", "task", task_id, timestamp),
            )
        return WorkspaceTask(id=task_id, project_id=project_id, status=TaskStatus.TODO, created_at=timestamp, updated_at=timestamp, **request.model_dump())

    async def create_task(self, project_id: str, request: TaskCreateRequest) -> WorkspaceTask:
        await self.initialize()
        return await asyncio.to_thread(self._create_task_sync, project_id, new_id(), request)

    def _set_task_status_sync(self, task_id: str, status: TaskStatus) -> WorkspaceTask | None:
        with self._connect() as connection:
            cursor = connection.execute("UPDATE workspace_tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now(), task_id))
            if cursor.rowcount != 1:
                return None
            row = connection.execute("SELECT * FROM workspace_tasks WHERE id = ?", (task_id,)).fetchone()
        return self._task(row)

    async def set_task_status(self, task_id: str, status: TaskStatus) -> WorkspaceTask | None:
        await self.initialize()
        return await asyncio.to_thread(self._set_task_status_sync, task_id, status)

    def _snapshot_sync(self, project_id: str) -> WorkspaceSnapshot | None:
        with self._connect() as connection:
            project = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if project is None:
                return None
            modules = connection.execute("SELECT * FROM modules WHERE project_id = ? ORDER BY created_at", (project_id,)).fetchall()
            notes = connection.execute("SELECT * FROM notes WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
            tasks = connection.execute("SELECT * FROM workspace_tasks WHERE project_id = ? ORDER BY updated_at DESC", (project_id,)).fetchall()
            markers = connection.execute("SELECT * FROM module_markers WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
        return WorkspaceSnapshot(project=self._project(project), modules=[self._module(row) for row in modules], notes=[self._note(row) for row in notes], tasks=[self._task(row) for row in tasks], markers=[self._marker(row) for row in markers])

    async def snapshot(self, project_id: str) -> WorkspaceSnapshot | None:
        await self.initialize()
        return await asyncio.to_thread(self._snapshot_sync, project_id)


_store: WorkspaceStore | None = None


def get_workspace_store(run_store: SQLiteRunStore) -> WorkspaceStore:
    global _store
    if _store is None or _store.run_store is not run_store:
        _store = WorkspaceStore(run_store)
    return _store
