from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import subprocess
import tomllib
import secrets
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.storage import SQLiteRunStore

from .models import (
    DevicePairing,
    DevicePairingRequest,
    DeviceRegistration,
    DeviceRegistrationRequest,
    DeviceStatus,
    DeviceSyncRequest,
    DeviceSyncResponse,
    GraphitiEpisodeEnvelope,
    LocalRepositoryInventory,
    MarkerType,
    ModuleCreateRequest,
    NoteCreateRequest,
    ProjectCreateRequest,
    ProjectDevice,
    ProjectEvent,
    ProjectEventMutation,
    ProjectEventType,
    RepositoryDependency,
    RepositoryFile,
    RepositoryIndex,
    SyncConflict,
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
    origin TEXT NOT NULL DEFAULT 'manual',
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

CREATE TABLE IF NOT EXISTS repository_indexes (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    repository_url TEXT NOT NULL,
    branch TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    files_count INTEGER NOT NULL,
    modules_count INTEGER NOT NULL,
    dependencies_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS repository_files (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    language TEXT,
    size INTEGER,
    PRIMARY KEY (project_id, path)
);

CREATE INDEX IF NOT EXISTS idx_modules_project ON modules(project_id);
CREATE INDEX IF NOT EXISTS idx_notes_project_module ON notes(project_id, module_id);
CREATE INDEX IF NOT EXISTS idx_workspace_tasks_project_module ON workspace_tasks(project_id, module_id);
CREATE INDEX IF NOT EXISTS idx_markers_project_module ON module_markers(project_id, module_id);
CREATE INDEX IF NOT EXISTS idx_repository_files_project ON repository_files(project_id, kind, path);

CREATE TABLE IF NOT EXISTS project_devices (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    device_token_hash TEXT NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'offline',
    runtime_version TEXT NOT NULL,
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    inventory_json TEXT NOT NULL DEFAULT '{}',
    last_seen_at TEXT,
    last_synced_at TEXT,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS device_pairings (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_user_id TEXT NOT NULL,
    name_hint TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    event_id TEXT NOT NULL,
    device_id TEXT REFERENCES project_devices(id) ON DELETE SET NULL,
    actor_id TEXT,
    type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    base_revision INTEGER NOT NULL DEFAULT 0,
    entity_revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, event_id)
);

CREATE TABLE IF NOT EXISTS project_entity_revisions (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    PRIMARY KEY(project_id, entity_id)
);

CREATE TABLE IF NOT EXISTS graphiti_episode_envelopes (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    episode_id TEXT NOT NULL,
    device_id TEXT REFERENCES project_devices(id) ON DELETE SET NULL,
    envelope_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(project_id, episode_id)
);

CREATE INDEX IF NOT EXISTS idx_project_devices_project ON project_devices(project_id, status);
CREATE INDEX IF NOT EXISTS idx_project_events_project_sequence ON project_events(project_id, sequence);
CREATE INDEX IF NOT EXISTS idx_device_pairings_token ON device_pairings(token_hash);
"""

LEGACY_DEFAULT_SCOPES = {
    "src/orchestrator",
    "frontend/client/src/hooks/useChat.ts",
    "src/storage/run_store.py",
    "src/policy",
    "frontend/client/src/components/TaskGraph.tsx",
}

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".html", ".sql"}
LANGUAGES = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TSX",
    ".js": "JavaScript",
    ".jsx": "JSX",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".css": "CSS",
    ".html": "HTML",
    ".json": "JSON",
    ".md": "Markdown",
    ".toml": "TOML",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".sh": "Shell",
    ".sql": "SQL",
    ".dockerfile": "Dockerfile",
}
PYTHON_IMPORT = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE)
PYTHON_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9_.-]+)(.*)$")
JS_IMPORT = re.compile(r"(?:import|export)\s+(?:[^'\";]+?\s+from\s+)?['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\s*\)")


def now() -> str:
    return datetime.now(UTC).isoformat()


def module_id(project_id: str, source_scope: str) -> str:
    digest = hashlib.sha256(f"{project_id}:{source_scope}".encode("utf-8")).hexdigest()[:24]
    return f"git-{digest}"


def language_for(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    if path.lower().endswith("dockerfile"):
        return "Dockerfile"
    return LANGUAGES.get(suffix)


def module_scope(path: str) -> str | None:
    parts = Path(path).parts
    if Path(path).suffix.lower() not in SOURCE_SUFFIXES:
        return None
    if len(parts) >= 2 and parts[0] == "src":
        return "/".join(parts[:2])
    if len(parts) >= 4 and parts[:3] == ("frontend", "client", "src"):
        return "/".join(parts[:4])
    if parts and parts[0] == "tests":
        return "tests"
    return None


def module_kind(scope: str) -> str:
    if scope.startswith("frontend/"):
        return "frontend"
    if scope.startswith("src/"):
        return "backend"
    if scope == "tests":
        return "test"
    return "repository"


def title_for_scope(scope: str) -> str:
    return scope.replace("/", " · ").replace("_", " ").title()


class WorkspaceStore:
    """Durable workspace context plus a Git-derived, read-only project map."""

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
                columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(modules)").fetchall()}
                if "origin" not in columns:
                    connection.execute("ALTER TABLE modules ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'")

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
            status=row["status"], origin=row["origin"] if "origin" in row.keys() else "manual", created_at=row["created_at"], updated_at=row["updated_at"],
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

    @staticmethod
    def _repository_index(row: sqlite3.Row) -> RepositoryIndex:
        return RepositoryIndex(
            project_id=row["project_id"], repository_url=row["repository_url"], branch=row["branch"], commit_sha=row["commit_sha"],
            indexed_at=row["indexed_at"], files_count=row["files_count"], modules_count=row["modules_count"],
            dependencies=[RepositoryDependency.model_validate(item) for item in json.loads(row["dependencies_json"])],
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
                    ("default", "AI Agent Platform", "Git-derived product workspace for the agent platform.", timestamp, timestamp),
                )
                return WorkspaceProject(id="default", name="AI Agent Platform", description="Git-derived product workspace for the agent platform.", created_at=timestamp, updated_at=timestamp)

        return await asyncio.to_thread(create_default)

    def _get_project_sync(self, project_id: str) -> WorkspaceProject | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._project(row) if row else None

    async def get_project(self, project_id: str) -> WorkspaceProject | None:
        await self.initialize()
        return await asyncio.to_thread(self._get_project_sync, project_id)

    def _create_module_sync(self, project_id: str, module_id_value: str, request: ModuleCreateRequest) -> WorkspaceModule:
        timestamp = now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO modules (id, project_id, title, kind, source_scope, aliases_json, dependencies_json, position_x, position_y, status, origin, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (module_id_value, project_id, request.title, request.kind, request.source_scope, json.dumps(request.aliases), json.dumps(request.dependencies), request.position_x, request.position_y, request.status, "manual", timestamp, timestamp),
            )
        return WorkspaceModule(id=module_id_value, project_id=project_id, origin="manual", created_at=timestamp, updated_at=timestamp, **request.model_dump())

    async def create_module(self, project_id: str, request: ModuleCreateRequest) -> WorkspaceModule:
        await self.initialize()
        return await asyncio.to_thread(self._create_module_sync, project_id, new_id(), request)

    def _module_belongs_to_project(self, connection: sqlite3.Connection, project_id: str, module_id_value: str) -> bool:
        return connection.execute("SELECT 1 FROM modules WHERE id = ? AND project_id = ?", (module_id_value, project_id)).fetchone() is not None

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

    @staticmethod
    def _run_git(repo_root: Path, *args: str) -> str:
        try:
            completed = subprocess.run(
                ["git", "-C", str(repo_root), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("The configured workspace is not a readable Git repository") from exc
        return completed.stdout.strip()

    @staticmethod
    def _tracked_files(repo_root: Path) -> list[str]:
        output = WorkspaceStore._run_git(repo_root, "ls-files", "-z")
        return sorted(path for path in output.split("\0") if path and not path.startswith(".git/"))

    @staticmethod
    def _repository_files(repo_root: Path, tracked_paths: Iterable[str]) -> list[RepositoryFile]:
        directories: set[str] = set()
        files: list[RepositoryFile] = []
        for raw_path in tracked_paths:
            relative = Path(raw_path)
            for parent in relative.parents:
                if parent != Path("."):
                    directories.add(parent.as_posix())
            full_path = repo_root / relative
            size = full_path.stat().st_size if full_path.is_file() else None
            files.append(RepositoryFile(path=relative.as_posix(), kind="file", language=language_for(relative.as_posix()), size=size))
        directory_items = [RepositoryFile(path=path, kind="directory") for path in sorted(directories)]
        return [*directory_items, *files]

    @staticmethod
    def _read_text(repo_root: Path, relative_path: str) -> str:
        try:
            return (repo_root / relative_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    @staticmethod
    def _python_dependency(requirement: str, group: str) -> RepositoryDependency:
        normalized = requirement.split(";", 1)[0].strip()
        match = PYTHON_REQUIREMENT.match(normalized)
        if match is None:
            return RepositoryDependency(name=normalized, ecosystem="python", group=group)
        return RepositoryDependency(name=match.group(1), ecosystem="python", version=match.group(2).strip(), group=group)

    @classmethod
    def _dependencies(cls, repo_root: Path, tracked_paths: set[str]) -> list[RepositoryDependency]:
        dependencies: list[RepositoryDependency] = []
        if "pyproject.toml" in tracked_paths:
            try:
                config = tomllib.loads(cls._read_text(repo_root, "pyproject.toml"))
            except tomllib.TOMLDecodeError:
                config = {}
            project = config.get("project", {}) if isinstance(config, dict) else {}
            for requirement in project.get("dependencies", []) if isinstance(project, dict) else []:
                dependencies.append(cls._python_dependency(str(requirement), "production"))
            optional = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
            if isinstance(optional, dict):
                for group, values in optional.items():
                    for requirement in values if isinstance(values, list) else []:
                        dependencies.append(cls._python_dependency(str(requirement), str(group)))
        for manifest in sorted(path for path in tracked_paths if path.endswith("package.json")):
            try:
                package = json.loads(cls._read_text(repo_root, manifest))
            except json.JSONDecodeError:
                package = {}
            for group, key in (("production", "dependencies"), ("development", "devDependencies")):
                entries = package.get(key, {}) if isinstance(package, dict) else {}
                if isinstance(entries, dict):
                    dependencies.extend(RepositoryDependency(name=str(name), ecosystem="node", version=str(version), group=group) for name, version in entries.items())
        unique: dict[tuple[str, str, str], RepositoryDependency] = {}
        for dependency in dependencies:
            unique[(dependency.ecosystem, dependency.group, dependency.name)] = dependency
        return sorted(unique.values(), key=lambda item: (item.ecosystem, item.group, item.name.lower()))

    @classmethod
    def _module_import_scopes(cls, repo_root: Path, path: str, available_scopes: set[str]) -> set[str]:
        content = cls._read_text(repo_root, path)
        source = Path(path)
        scopes: set[str] = set()
        if source.suffix == ".py":
            for match in PYTHON_IMPORT.finditer(content):
                package = match.group(1)
                candidate = "/".join(package.split(".")[:2])
                if candidate in available_scopes:
                    scopes.add(candidate)
        elif source.suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            for match in JS_IMPORT.finditer(content):
                raw_target = match.group(1) or match.group(2)
                if not raw_target or not raw_target.startswith("."):
                    continue
                resolved = (source.parent / raw_target).resolve()
                try:
                    relative = resolved.relative_to(repo_root.resolve()).as_posix()
                except ValueError:
                    continue
                for suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
                    scope = module_scope(relative + suffix) if Path(relative).suffix == "" else module_scope(relative)
                    if scope in available_scopes:
                        scopes.add(scope)
        return scopes

    @classmethod
    def _derived_modules(cls, project_id: str, repo_root: Path, tracked_paths: list[str]) -> list[dict[str, Any]]:
        scopes = sorted({scope for path in tracked_paths if (scope := module_scope(path)) is not None})
        scope_set = set(scopes)
        grouped: dict[str, list[str]] = {scope: [] for scope in scopes}
        for path in tracked_paths:
            scope = module_scope(path)
            if scope is not None:
                grouped[scope].append(path)
        modules: list[dict[str, Any]] = []
        for index, scope in enumerate(scopes):
            dependency_scopes: set[str] = set()
            for path in grouped[scope]:
                dependency_scopes.update(cls._module_import_scopes(repo_root, path, scope_set))
            dependency_scopes.discard(scope)
            modules.append(
                {
                    "id": module_id(project_id, scope),
                    "title": title_for_scope(scope),
                    "kind": module_kind(scope),
                    "source_scope": scope,
                    "aliases": sorted({scope.split("/")[-1], *scope.replace("/", " ").split()}),
                    "dependencies": [module_id(project_id, dependency) for dependency in sorted(dependency_scopes)],
                    "position_x": float(80 + (index % 4) * 300),
                    "position_y": float(120 + (index // 4) * 190),
                }
            )
        return modules

    def _index_repository_sync(self, project_id: str, repo_path: str | Path) -> RepositoryIndex:
        repo_root = Path(repo_path).resolve()
        if not repo_root.is_dir():
            raise RuntimeError("Configured repository path does not exist")
        tracked_paths = self._tracked_files(repo_root)
        tracked_set = set(tracked_paths)
        files = self._repository_files(repo_root, tracked_paths)
        dependencies = self._dependencies(repo_root, tracked_set)
        modules = self._derived_modules(project_id, repo_root, tracked_paths)
        repository_url = self._run_git(repo_root, "config", "--get", "remote.origin.url") or "local"
        branch = self._run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
        commit_sha = self._run_git(repo_root, "rev-parse", "HEAD")
        indexed_at = now()

        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                raise LookupError("Project not found")
            connection.execute("DELETE FROM repository_files WHERE project_id = ?", (project_id,))
            connection.executemany(
                "INSERT INTO repository_files (project_id, path, kind, language, size) VALUES (?, ?, ?, ?, ?)",
                [(project_id, item.path, item.kind, item.language, item.size) for item in files],
            )
            retained_git_ids = [item["id"] for item in modules]
            if retained_git_ids:
                placeholders = ",".join("?" for _ in retained_git_ids)
                connection.execute(
                    f"DELETE FROM modules WHERE project_id = ? AND origin = 'git' AND id NOT IN ({placeholders}) AND NOT EXISTS (SELECT 1 FROM notes WHERE notes.module_id = modules.id) AND NOT EXISTS (SELECT 1 FROM workspace_tasks WHERE workspace_tasks.module_id = modules.id)",
                    [project_id, *retained_git_ids],
                )
                connection.execute(
                    f"UPDATE modules SET status = 'orphaned', updated_at = ? WHERE project_id = ? AND origin = 'git' AND id NOT IN ({placeholders})",
                    [indexed_at, project_id, *retained_git_ids],
                )
            else:
                connection.execute(
                    "DELETE FROM modules WHERE project_id = ? AND origin = 'git' AND NOT EXISTS (SELECT 1 FROM notes WHERE notes.module_id = modules.id) AND NOT EXISTS (SELECT 1 FROM workspace_tasks WHERE workspace_tasks.module_id = modules.id)",
                    (project_id,),
                )
                connection.execute("UPDATE modules SET status = 'orphaned', updated_at = ? WHERE project_id = ? AND origin = 'git'", (indexed_at, project_id))
            for scope in LEGACY_DEFAULT_SCOPES:
                connection.execute(
                    "DELETE FROM modules WHERE project_id = ? AND source_scope = ? AND origin = 'manual' AND NOT EXISTS (SELECT 1 FROM notes WHERE notes.module_id = modules.id) AND NOT EXISTS (SELECT 1 FROM workspace_tasks WHERE workspace_tasks.module_id = modules.id)",
                    (project_id, scope),
                )
            connection.executemany(
                "INSERT INTO modules (id, project_id, title, kind, source_scope, aliases_json, dependencies_json, position_x, position_y, status, origin, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'git', ?, ?) ON CONFLICT(id) DO UPDATE SET title = excluded.title, kind = excluded.kind, source_scope = excluded.source_scope, aliases_json = excluded.aliases_json, dependencies_json = excluded.dependencies_json, position_x = excluded.position_x, position_y = excluded.position_y, status = 'active', origin = 'git', updated_at = excluded.updated_at",
                [
                    (item["id"], project_id, item["title"], item["kind"], item["source_scope"], json.dumps(item["aliases"]), json.dumps(item["dependencies"]), item["position_x"], item["position_y"], "active", indexed_at, indexed_at)
                    for item in modules
                ],
            )
            connection.execute(
                "INSERT INTO repository_indexes (project_id, repository_url, branch, commit_sha, indexed_at, files_count, modules_count, dependencies_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(project_id) DO UPDATE SET repository_url = excluded.repository_url, branch = excluded.branch, commit_sha = excluded.commit_sha, indexed_at = excluded.indexed_at, files_count = excluded.files_count, modules_count = excluded.modules_count, dependencies_json = excluded.dependencies_json",
                (project_id, repository_url, branch, commit_sha, indexed_at, len([item for item in files if item.kind == "file"]), len(modules), json.dumps([item.model_dump() for item in dependencies])),
            )
            connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (indexed_at, project_id))
        return RepositoryIndex(project_id=project_id, repository_url=repository_url, branch=branch, commit_sha=commit_sha, indexed_at=indexed_at, files_count=len([item for item in files if item.kind == "file"]), modules_count=len(modules), dependencies=dependencies)

    async def index_repository(self, project_id: str, repo_path: str | Path) -> RepositoryIndex:
        await self.initialize()
        return await asyncio.to_thread(self._index_repository_sync, project_id, repo_path)

    def _repository_files_sync(self, project_id: str) -> list[RepositoryFile]:
        with self._connect() as connection:
            rows = connection.execute("SELECT path, kind, language, size FROM repository_files WHERE project_id = ? ORDER BY kind DESC, path", (project_id,)).fetchall()
        return [RepositoryFile(path=row["path"], kind=row["kind"], language=row["language"], size=row["size"]) for row in rows]

    async def repository_files(self, project_id: str) -> list[RepositoryFile]:
        await self.initialize()
        return await asyncio.to_thread(self._repository_files_sync, project_id)

    def _repository_index_sync(self, project_id: str) -> RepositoryIndex | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM repository_indexes WHERE project_id = ?", (project_id,)).fetchone()
        return self._repository_index(row) if row else None

    async def repository_index(self, project_id: str) -> RepositoryIndex | None:
        await self.initialize()
        return await asyncio.to_thread(self._repository_index_sync, project_id)

    def _snapshot_sync(self, project_id: str) -> WorkspaceSnapshot | None:
        with self._connect() as connection:
            project = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if project is None:
                return None
            modules = connection.execute("SELECT * FROM modules WHERE project_id = ? ORDER BY origin DESC, source_scope", (project_id,)).fetchall()
            notes = connection.execute("SELECT * FROM notes WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
            tasks = connection.execute("SELECT * FROM workspace_tasks WHERE project_id = ? ORDER BY updated_at DESC", (project_id,)).fetchall()
            markers = connection.execute("SELECT * FROM module_markers WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
        return WorkspaceSnapshot(project=self._project(project), modules=[self._module(row) for row in modules], notes=[self._note(row) for row in notes], tasks=[self._task(row) for row in tasks], markers=[self._marker(row) for row in markers])

    async def snapshot(self, project_id: str) -> WorkspaceSnapshot | None:
        await self.initialize()
        return await asyncio.to_thread(self._snapshot_sync, project_id)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _inventory_from_row(row: sqlite3.Row) -> LocalRepositoryInventory | None:
        raw = str(row["inventory_json"] or "")
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return LocalRepositoryInventory.model_validate(payload) if payload else None

    @classmethod
    def _device(cls, row: sqlite3.Row) -> ProjectDevice:
        return ProjectDevice(
            id=row["id"], project_id=row["project_id"], owner_user_id=row["owner_user_id"], name=row["name"],
            status=DeviceStatus(row["status"]), runtime_version=row["runtime_version"], capabilities=json.loads(row["capabilities_json"]),
            inventory=cls._inventory_from_row(row), last_seen_at=row["last_seen_at"], last_synced_at=row["last_synced_at"],
            created_at=row["created_at"], revoked_at=row["revoked_at"],
        )

    @staticmethod
    def _event(row: sqlite3.Row) -> ProjectEvent:
        return ProjectEvent(
            sequence=int(row["sequence"]), project_id=row["project_id"], event_id=row["event_id"], device_id=row["device_id"],
            actor_id=row["actor_id"], type=ProjectEventType(row["type"]), entity_id=row["entity_id"], base_revision=int(row["base_revision"]),
            entity_revision=int(row["entity_revision"]), payload=json.loads(row["payload_json"]), occurred_at=row["occurred_at"], created_at=row["created_at"],
        )

    def _create_device_pairing_sync(self, project_id: str, owner_user_id: str, request: DevicePairingRequest) -> DevicePairing:
        timestamp = now()
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds)).isoformat()
        pairing = DevicePairing(id=new_id(), project_id=project_id, name_hint=request.name_hint, pairing_token=token, expires_at=expires_at)
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                raise LookupError("Project not found")
            connection.execute(
                "INSERT INTO device_pairings (id, project_id, owner_user_id, name_hint, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pairing.id, project_id, owner_user_id, request.name_hint, self._token_hash(token), expires_at, timestamp),
            )
        return pairing

    async def create_device_pairing(self, project_id: str, owner_user_id: str, request: DevicePairingRequest) -> DevicePairing:
        await self.initialize()
        return await asyncio.to_thread(self._create_device_pairing_sync, project_id, owner_user_id, request)

    def _register_device_sync(self, project_id: str, request: DeviceRegistrationRequest) -> DeviceRegistration:
        token_hash = self._token_hash(request.pairing_token)
        timestamp = now()
        device_token = secrets.token_urlsafe(48)
        device_id = new_id()
        with self._connect() as connection:
            pairing = connection.execute(
                "SELECT * FROM device_pairings WHERE project_id = ? AND token_hash = ? AND consumed_at IS NULL", (project_id, token_hash)
            ).fetchone()
            if pairing is None:
                raise PermissionError("Pairing token is invalid or already consumed")
            try:
                expires_at = datetime.fromisoformat(str(pairing["expires_at"]).replace("Z", "+00:00"))
            except ValueError as exc:
                raise PermissionError("Pairing token is invalid") from exc
            if expires_at <= datetime.now(UTC):
                raise PermissionError("Pairing token has expired")
            inventory_json = json.dumps(request.inventory.model_dump()) if request.inventory is not None else ""
            connection.execute(
                "INSERT INTO project_devices (id, project_id, owner_user_id, name, device_token_hash, public_key, status, runtime_version, capabilities_json, inventory_json, last_seen_at, last_synced_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (device_id, project_id, pairing["owner_user_id"], request.name, self._token_hash(device_token), request.public_key, DeviceStatus.ONLINE, request.runtime_version, json.dumps(sorted(set(request.capabilities))), inventory_json, timestamp, timestamp, timestamp),
            )
            connection.execute("UPDATE device_pairings SET consumed_at = ? WHERE id = ?", (timestamp, pairing["id"]))
            row = connection.execute("SELECT * FROM project_devices WHERE id = ?", (device_id,)).fetchone()
        return DeviceRegistration(**self._device(row).model_dump(), device_token=device_token)

    async def register_device(self, project_id: str, request: DeviceRegistrationRequest) -> DeviceRegistration:
        await self.initialize()
        return await asyncio.to_thread(self._register_device_sync, project_id, request)

    def _list_devices_sync(self, project_id: str) -> list[ProjectDevice]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM project_devices WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()
        return [self._device(row) for row in rows]

    async def list_devices(self, project_id: str) -> list[ProjectDevice]:
        await self.initialize()
        return await asyncio.to_thread(self._list_devices_sync, project_id)

    def _authenticate_device_sync(self, project_id: str, device_token: str) -> ProjectDevice | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM project_devices WHERE project_id = ? AND device_token_hash = ?", (project_id, self._token_hash(device_token))
            ).fetchone()
        if row is None or row["status"] == DeviceStatus.REVOKED:
            return None
        return self._device(row)

    async def authenticate_device(self, project_id: str, device_token: str) -> ProjectDevice | None:
        await self.initialize()
        return await asyncio.to_thread(self._authenticate_device_sync, project_id, device_token)

    def _apply_remote_projection(self, connection: sqlite3.Connection, project_id: str, event: ProjectEventMutation) -> None:
        payload = event.payload
        if event.type == ProjectEventType.NOTE_CREATED:
            request = NoteCreateRequest.model_validate(payload)
            if not self._module_belongs_to_project(connection, project_id, request.module_id):
                raise LookupError("Module not found in project")
            connection.execute(
                "INSERT INTO notes (id, project_id, module_id, title, content, kind, author, source_run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event.entity_id, project_id, request.module_id, request.title, request.content, request.kind, str(payload.get("author", "local-runtime")), request.source_run_id, event.occurred_at),
            )
            connection.execute(
                "INSERT INTO module_markers (id, project_id, module_id, type, title, state, source_kind, source_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), project_id, request.module_id, request.kind, request.title, "open", "note", event.entity_id, event.occurred_at),
            )
        elif event.type == ProjectEventType.TASK_CREATED:
            request = TaskCreateRequest.model_validate(payload)
            if not self._module_belongs_to_project(connection, project_id, request.module_id):
                raise LookupError("Module not found in project")
            connection.execute(
                "INSERT INTO workspace_tasks (id, project_id, module_id, title, description, acceptance_criteria_json, status, priority, source_run_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event.entity_id, project_id, request.module_id, request.title, request.description, json.dumps(request.acceptance_criteria), TaskStatus.TODO, request.priority, request.source_run_id, event.occurred_at, event.occurred_at),
            )
            connection.execute(
                "INSERT INTO module_markers (id, project_id, module_id, type, title, state, source_kind, source_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), project_id, request.module_id, MarkerType.TASK, request.title, "open", "task", event.entity_id, event.occurred_at),
            )
        elif event.type == ProjectEventType.TASK_STATUS_CHANGED:
            status = TaskStatus(str(payload.get("status", "")))
            cursor = connection.execute("UPDATE workspace_tasks SET status = ?, updated_at = ? WHERE id = ? AND project_id = ?", (status, event.occurred_at, event.entity_id, project_id))
            if cursor.rowcount != 1:
                raise LookupError("Task not found in project")
        elif event.type == ProjectEventType.MARKER_CREATED:
            marker = WorkspaceMarker.model_validate({"id": event.entity_id, "project_id": project_id, **payload, "created_at": event.occurred_at})
            if not self._module_belongs_to_project(connection, project_id, marker.module_id):
                raise LookupError("Module not found in project")
            connection.execute(
                "INSERT INTO module_markers (id, project_id, module_id, type, title, state, source_kind, source_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (marker.id, project_id, marker.module_id, marker.type, marker.title, marker.state, marker.source_kind, marker.source_id, marker.created_at),
            )
        elif event.type == ProjectEventType.GRAPHITI_EPISODE:
            envelope = GraphitiEpisodeEnvelope.model_validate(payload)
            connection.execute(
                "INSERT INTO graphiti_episode_envelopes (project_id, episode_id, device_id, envelope_json, created_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(project_id, episode_id) DO NOTHING",
                (project_id, envelope.episode_id, None, json.dumps(envelope.model_dump()), now()),
            )

    def _sync_device_sync(self, project_id: str, device_id: str, request: DeviceSyncRequest) -> DeviceSyncResponse:
        timestamp = now()
        accepted: list[str] = []
        conflicts: list[SyncConflict] = []
        with self._connect() as connection:
            device = connection.execute("SELECT * FROM project_devices WHERE id = ? AND project_id = ?", (device_id, project_id)).fetchone()
            if device is None or device["status"] == DeviceStatus.REVOKED:
                raise PermissionError("Device is not authorized")
            inventory_json = json.dumps(request.inventory.model_dump()) if request.inventory is not None else device["inventory_json"]
            connection.execute(
                "UPDATE project_devices SET status = ?, inventory_json = ?, last_seen_at = ? WHERE id = ?", (DeviceStatus.ONLINE, inventory_json, timestamp, device_id)
            )
            for mutation in request.events:
                existing = connection.execute("SELECT sequence FROM project_events WHERE project_id = ? AND event_id = ?", (project_id, mutation.event_id)).fetchone()
                if existing is not None:
                    accepted.append(mutation.event_id)
                    continue
                revision_row = connection.execute("SELECT revision FROM project_entity_revisions WHERE project_id = ? AND entity_id = ?", (project_id, mutation.entity_id)).fetchone()
                current_revision = int(revision_row["revision"]) if revision_row is not None else 0
                if mutation.base_revision != current_revision:
                    conflicts.append(SyncConflict(event_id=mutation.event_id, code="revision_conflict", detail="The entity changed while this device was offline", entity_id=mutation.entity_id, current_revision=current_revision))
                    continue
                try:
                    self._apply_remote_projection(connection, project_id, mutation)
                except (LookupError, ValueError) as exc:
                    conflicts.append(SyncConflict(event_id=mutation.event_id, code="projection_rejected", detail=str(exc), entity_id=mutation.entity_id, current_revision=current_revision))
                    continue
                next_revision = current_revision + 1
                connection.execute(
                    "INSERT INTO project_entity_revisions (project_id, entity_id, revision) VALUES (?, ?, ?) ON CONFLICT(project_id, entity_id) DO UPDATE SET revision = excluded.revision",
                    (project_id, mutation.entity_id, next_revision),
                )
                connection.execute(
                    "INSERT INTO project_events (project_id, event_id, device_id, actor_id, type, entity_id, base_revision, entity_revision, payload_json, occurred_at, created_at) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)",
                    (project_id, mutation.event_id, device_id, mutation.type, mutation.entity_id, mutation.base_revision, next_revision, json.dumps(mutation.payload), mutation.occurred_at, timestamp),
                )
                accepted.append(mutation.event_id)
            events = connection.execute("SELECT * FROM project_events WHERE project_id = ? AND sequence > ? ORDER BY sequence LIMIT 500", (project_id, request.cursor)).fetchall()
            cursor_row = connection.execute("SELECT COALESCE(MAX(sequence), 0) AS cursor FROM project_events WHERE project_id = ?", (project_id,)).fetchone()
            server_cursor = int(cursor_row["cursor"])
            connection.execute("UPDATE project_devices SET last_synced_at = ? WHERE id = ?", (timestamp, device_id))
            updated_device = connection.execute("SELECT * FROM project_devices WHERE id = ?", (device_id,)).fetchone()
        return DeviceSyncResponse(accepted_event_ids=accepted, conflicts=conflicts, events=[self._event(row) for row in events], server_cursor=server_cursor, device=self._device(updated_device))

    async def sync_device(self, project_id: str, device_id: str, request: DeviceSyncRequest) -> DeviceSyncResponse:
        await self.initialize()
        return await asyncio.to_thread(self._sync_device_sync, project_id, device_id, request)

    def _record_cloud_event_sync(self, project_id: str, actor_id: str | None, event_type: ProjectEventType, entity_id: str, payload: dict[str, Any], occurred_at: str | None = None) -> ProjectEvent:
        timestamp = now()
        with self._connect() as connection:
            revision_row = connection.execute("SELECT revision FROM project_entity_revisions WHERE project_id = ? AND entity_id = ?", (project_id, entity_id)).fetchone()
            base_revision = int(revision_row["revision"]) if revision_row is not None else 0
            entity_revision = base_revision + 1
            connection.execute(
                "INSERT INTO project_entity_revisions (project_id, entity_id, revision) VALUES (?, ?, ?) ON CONFLICT(project_id, entity_id) DO UPDATE SET revision = excluded.revision",
                (project_id, entity_id, entity_revision),
            )
            event_timestamp = occurred_at or timestamp
            if event_type == ProjectEventType.GRAPHITI_EPISODE:
                envelope = GraphitiEpisodeEnvelope.model_validate(payload)
                connection.execute(
                    "INSERT INTO graphiti_episode_envelopes (project_id, episode_id, device_id, envelope_json, created_at) VALUES (?, ?, NULL, ?, ?) ON CONFLICT(project_id, episode_id) DO NOTHING",
                    (project_id, envelope.episode_id, json.dumps(envelope.model_dump()), timestamp),
                )
            cursor = connection.execute(
                "INSERT INTO project_events (project_id, event_id, device_id, actor_id, type, entity_id, base_revision, entity_revision, payload_json, occurred_at, created_at) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, new_id(), actor_id, event_type, entity_id, base_revision, entity_revision, json.dumps(payload), event_timestamp, timestamp),
            )
            row = connection.execute("SELECT * FROM project_events WHERE sequence = ?", (cursor.lastrowid,)).fetchone()
        return self._event(row)

    async def record_cloud_event(self, project_id: str, actor_id: str | None, event_type: ProjectEventType, entity_id: str, payload: dict[str, Any], occurred_at: str | None = None) -> ProjectEvent:
        await self.initialize()
        return await asyncio.to_thread(self._record_cloud_event_sync, project_id, actor_id, event_type, entity_id, payload, occurred_at)

    def _graphiti_episodes_sync(self, project_id: str, limit: int = 100) -> list[GraphitiEpisodeEnvelope]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT envelope_json FROM graphiti_episode_envelopes WHERE project_id = ? ORDER BY created_at DESC LIMIT ?", (project_id, limit)
            ).fetchall()
        return [GraphitiEpisodeEnvelope.model_validate(json.loads(row["envelope_json"])) for row in rows]

    async def graphiti_episodes(self, project_id: str, limit: int = 100) -> list[GraphitiEpisodeEnvelope]:
        await self.initialize()
        return await asyncio.to_thread(self._graphiti_episodes_sync, project_id, limit)


_store: WorkspaceStore | None = None


def get_workspace_store(run_store: SQLiteRunStore) -> WorkspaceStore:
    global _store
    if _store is None or _store.run_store is not run_store:
        _store = WorkspaceStore(run_store)
    return _store
