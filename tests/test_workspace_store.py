from __future__ import annotations

import pytest

from src.storage.run_store import SQLiteRunStore
from src.workspace import NoteCreateRequest, TaskCreateRequest, TaskStatus, get_workspace_store


@pytest.mark.asyncio
async def test_workspace_persists_modules_notes_tasks_and_markers(tmp_path):
    run_store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    store = get_workspace_store(run_store)

    project = await store.ensure_default_project()
    first_snapshot = await store.snapshot(project.id)
    assert first_snapshot is not None
    assert len(first_snapshot.modules) == 5
    module = first_snapshot.modules[0]

    note = await store.create_note(
        project.id,
        NoteCreateRequest(module_id=module.id, title="Contract decision", content="Keep the response contract typed and durable."),
    )
    task = await store.create_task(
        project.id,
        TaskCreateRequest(module_id=module.id, title="Add workspace markers", acceptance_criteria=["Marker appears on module"]),
    )
    completed = await store.set_task_status(task.id, TaskStatus.DONE)
    final_snapshot = await store.snapshot(project.id)

    assert completed is not None and completed.status == TaskStatus.DONE
    assert final_snapshot is not None
    assert [item.id for item in final_snapshot.notes] == [note.id]
    assert [item.id for item in final_snapshot.tasks] == [task.id]
    assert {marker.type for marker in final_snapshot.markers} == {"note", "task"}


@pytest.mark.asyncio
async def test_workspace_api_returns_default_registry_and_persists_artifacts(monkeypatch, tmp_path):
    from httpx import ASGITransport, AsyncClient
    from src.api import routes
    from src.main import app

    run_store = SQLiteRunStore(str(tmp_path / "api-state.db"))
    monkeypatch.setattr(routes, "get_run_store", lambda: run_store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        projects = await client.get("/v1/projects")
        assert projects.status_code == 200
        project_id = projects.json()[0]["id"]
        snapshot = await client.get(f"/v1/projects/{project_id}/workspace")
        module_id = snapshot.json()["modules"][0]["id"]
        note = await client.post(f"/v1/projects/{project_id}/notes", json={"module_id": module_id, "title": "API note", "content": "Persisted from endpoint"})
        task = await client.post(f"/v1/projects/{project_id}/tasks", json={"module_id": module_id, "title": "API task"})
        final_snapshot = await client.get(f"/v1/projects/{project_id}/workspace")

    assert snapshot.status_code == 200
    assert note.status_code == 201
    assert task.status_code == 201
    assert {marker["type"] for marker in final_snapshot.json()["markers"]} == {"note", "task"}


@pytest.mark.asyncio
async def test_workspace_artifacts_preserve_source_run_provenance(tmp_path):
    run_store = SQLiteRunStore(str(tmp_path / "agent-state.db"))
    store = get_workspace_store(run_store)
    project = await store.ensure_default_project()
    snapshot = await store.snapshot(project.id)
    assert snapshot is not None
    module = snapshot.modules[0]

    note = await store.create_note(
        project.id,
        NoteCreateRequest(module_id=module.id, title="Run decision", content="Persist the reviewer outcome.", source_run_id="run-123"),
    )
    task = await store.create_task(
        project.id,
        TaskCreateRequest(module_id=module.id, title="Follow up", source_run_id="run-123"),
    )

    assert note.source_run_id == "run-123"
    assert task.source_run_id == "run-123"
