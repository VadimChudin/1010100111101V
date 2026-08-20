from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.storage.run_store import SQLiteRunStore
from src.workspace import NoteCreateRequest, TaskCreateRequest, TaskStatus, get_workspace_store


def create_repository(path: Path) -> Path:
    path.mkdir()
    (path / "src" / "api").mkdir(parents=True)
    (path / "frontend" / "client" / "src" / "components").mkdir(parents=True)
    (path / "src" / "api" / "main.py").write_text("from src.api import routes\n", encoding="utf-8")
    (path / "src" / "api" / "routes.py").write_text("def health():\n    return 'ok'\n", encoding="utf-8")
    (path / "frontend" / "client" / "src" / "components" / "App.tsx").write_text("export const App = () => <main />\n", encoding="utf-8")
    (path / "pyproject.toml").write_text(
        """[project]
name = "sample"
version = "0.1.0"
dependencies = ["fastapi>=0.115", "httpx>=0.27"]

[project.optional-dependencies]
test = ["pytest>=8"]
""",
        encoding="utf-8",
    )
    (path / "frontend" / "package.json").write_text(
        '{"dependencies":{"react":"^19.0.0"},"devDependencies":{"typescript":"^5.0.0"}}', encoding="utf-8"
    )
    for command in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "Test"],
        ["git", "add", "."],
        ["git", "commit", "--quiet", "-m", "Initial snapshot"],
    ):
        subprocess.run(command, cwd=path, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/example/sample.git"], cwd=path, check=True)
    return path


@pytest.mark.asyncio
async def test_workspace_indexes_git_tracked_files_dependencies_and_modules(tmp_path):
    repository = create_repository(tmp_path / "repository")
    run_store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    store = get_workspace_store(run_store)
    project = await store.ensure_default_project()

    index = await store.index_repository(project.id, repository)
    files = await store.repository_files(project.id)
    snapshot = await store.snapshot(project.id)

    assert index.repository_url == "https://github.com/example/sample.git"
    assert index.files_count == 5
    assert index.modules_count == 2
    assert {item.path for item in files if item.kind == "file"} >= {"src/api/main.py", "src/api/routes.py", "pyproject.toml", "frontend/package.json"}
    assert {dependency.name for dependency in index.dependencies} >= {"fastapi", "httpx", "react", "typescript"}
    assert {dependency.version for dependency in index.dependencies if dependency.name == "fastapi"} == {">=0.115"}
    assert snapshot is not None
    assert {module.source_scope for module in snapshot.modules} == {"src/api", "frontend/client/src/components"}
    assert all(module.origin == "git" for module in snapshot.modules)


@pytest.mark.asyncio
async def test_workspace_reindex_preserves_run_to_context_artifacts(tmp_path):
    repository = create_repository(tmp_path / "repository")
    run_store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    store = get_workspace_store(run_store)
    project = await store.ensure_default_project()
    await store.index_repository(project.id, repository)
    snapshot = await store.snapshot(project.id)
    assert snapshot is not None
    module = next(item for item in snapshot.modules if item.source_scope == "src/api")

    note = await store.create_note(
        project.id,
        NoteCreateRequest(module_id=module.id, title="Run decision", content="Keep the response contract typed and durable.", source_run_id="run-123"),
    )
    task = await store.create_task(
        project.id,
        TaskCreateRequest(module_id=module.id, title="Follow up", acceptance_criteria=["Marker appears on module"], source_run_id="run-123"),
    )
    completed = await store.set_task_status(task.id, TaskStatus.DONE)
    await store.index_repository(project.id, repository)
    final_snapshot = await store.snapshot(project.id)

    assert completed is not None and completed.status == TaskStatus.DONE
    assert final_snapshot is not None
    assert [item.id for item in final_snapshot.notes] == [note.id]
    assert [item.id for item in final_snapshot.tasks] == [task.id]
    assert final_snapshot.modules[0].origin == "git"
    assert {marker.type for marker in final_snapshot.markers} == {"note", "task"}


@pytest.mark.asyncio
async def test_workspace_repository_api_returns_index_and_files(monkeypatch, tmp_path):
    from httpx import ASGITransport, AsyncClient

    from src.api import routes
    from src.config import Settings
    from src.main import app

    repository = create_repository(tmp_path / "repository")
    run_store = SQLiteRunStore(str(tmp_path / "api-state.db"))
    monkeypatch.setattr(routes, "get_run_store", lambda: run_store)
    monkeypatch.setattr(routes, "get_settings", lambda: Settings(workspace_root=str(repository)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        projects = await client.get("/v1/projects")
        assert projects.status_code == 200
        project_id = projects.json()[0]["id"]
        indexed = await client.post(f"/v1/projects/{project_id}/index")
        repository_response = await client.get(f"/v1/projects/{project_id}/repository")
        files = await client.get(f"/v1/projects/{project_id}/files")

    assert indexed.status_code == 200
    assert indexed.json()["files_count"] == 5
    assert repository_response.status_code == 200
    assert repository_response.json()["commit_sha"] == indexed.json()["commit_sha"]
    assert files.status_code == 200
    assert any(item["path"] == "src/api/main.py" and item["language"] == "Python" for item in files.json())
