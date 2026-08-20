from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.storage.run_store import SQLiteRunStore
from src.workspace import (
    DeviceJobCreateRequest,
    DeviceJobResultSubmission,
    DeviceJobStatus,
    DeviceJobType,
    DevicePairingRequest,
    DeviceRegistrationRequest,
    DeviceSyncRequest,
    LocalRepositoryInventory,
    LocalWorkspaceManifest,
    NoteCreateRequest,
    ProjectEventMutation,
    ProjectSourceKind,
    ProjectSourceSelectionRequest,
    ProjectEventType,
    TaskCreateRequest,
    TaskStatus,
    get_workspace_store,
)


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


@pytest.mark.asyncio
async def test_device_pairing_outbox_sync_and_cloud_catch_up(tmp_path):
    repository = create_repository(tmp_path / "repository")
    run_store = SQLiteRunStore(str(tmp_path / "hybrid-state.db"))
    store = get_workspace_store(run_store)
    project = await store.ensure_default_project()
    await store.index_repository(project.id, repository)
    snapshot = await store.snapshot(project.id)
    assert snapshot is not None
    module = next(item for item in snapshot.modules if item.source_scope == "src/api")

    pairing = await store.create_device_pairing(project.id, "owner-1", DevicePairingRequest(name_hint="Developer laptop"))
    registration = await store.register_device(
        project.id,
        DeviceRegistrationRequest(
            pairing_token=pairing.pairing_token,
            name="Developer laptop",
            public_key="local-public-key-material",
            capabilities=["serena.read_only", "graphiti.local"],
            inventory=LocalRepositoryInventory(branch="main", commit_sha="a" * 40, dirty=True, tracked_files=5),
        ),
    )
    assert registration.status == "online"
    assert registration.device_token

    note_event = ProjectEventMutation(
        event_id="evt-local-note-0001",
        type=ProjectEventType.NOTE_CREATED,
        entity_id="note-local-1",
        base_revision=0,
        payload={"module_id": module.id, "title": "Offline decision", "content": "Remember this after cloud work.", "kind": "decision"},
        occurred_at="2026-08-20T12:00:00+00:00",
    )
    first_sync = await store.sync_device(project.id, registration.id, DeviceSyncRequest(events=[note_event], inventory=registration.inventory))
    assert first_sync.accepted_event_ids == [note_event.event_id]
    assert first_sync.conflicts == []
    assert first_sync.server_cursor == 1

    duplicate_sync = await store.sync_device(project.id, registration.id, DeviceSyncRequest(cursor=0, events=[note_event]))
    assert duplicate_sync.accepted_event_ids == [note_event.event_id]
    assert duplicate_sync.server_cursor == 1

    cloud_event = await store.record_cloud_event(
        project.id,
        "owner-1",
        ProjectEventType.GRAPHITI_EPISODE,
        "episode-cloud-1",
        {
            "episode_id": "episode-cloud-1",
            "group_id": project.id,
            "name": "Cloud continuation",
            "content": "The user continued work while the local runtime was offline.",
            "occurred_at": "2026-08-20T12:05:00+00:00",
        },
    )
    catch_up = await store.sync_device(project.id, registration.id, DeviceSyncRequest(cursor=1))
    assert catch_up.server_cursor == cloud_event.sequence
    assert [event.entity_id for event in catch_up.events] == ["episode-cloud-1"]
    episodes = await store.graphiti_episodes(project.id)
    assert [episode.episode_id for episode in episodes] == ["episode-cloud-1"]

    conflict = ProjectEventMutation(
        event_id="evt-local-note-conflict",
        type=ProjectEventType.NOTE_CREATED,
        entity_id="note-local-1",
        base_revision=0,
        payload={"module_id": module.id, "title": "Conflicting offline edit", "content": "Must not overwrite the first decision."},
        occurred_at="2026-08-20T12:06:00+00:00",
    )
    conflict_sync = await store.sync_device(project.id, registration.id, DeviceSyncRequest(cursor=cloud_event.sequence, events=[conflict]))
    assert conflict_sync.accepted_event_ids == []
    assert conflict_sync.conflicts[0].code == "revision_conflict"
    assert conflict_sync.conflicts[0].current_revision == 1

    final_snapshot = await store.snapshot(project.id)
    assert final_snapshot is not None
    assert any(note.id == "note-local-1" for note in final_snapshot.notes)
    assert (await store.list_devices(project.id))[0].inventory is not None


@pytest.mark.asyncio
async def test_device_jobs_require_approval_then_deliver_over_device_sync(tmp_path):
    repository = create_repository(tmp_path / "repository")
    run_store = SQLiteRunStore(str(tmp_path / "device-jobs-state.db"))
    store = get_workspace_store(run_store)
    project = await store.ensure_default_project()
    await store.index_repository(project.id, repository)
    pairing = await store.create_device_pairing(project.id, "owner-1", DevicePairingRequest(name_hint="Semantic laptop"))
    registration = await store.register_device(
        project.id,
        DeviceRegistrationRequest(
            pairing_token=pairing.pairing_token,
            name="Semantic laptop",
            public_key="semantic-local-public-key-material",
            capabilities=["serena.read_only", "graphiti.local"],
            inventory=LocalRepositoryInventory(branch="main", commit_sha="c" * 40, tracked_files=5),
        ),
    )

    job = await store.create_device_job(
        project.id,
        "editor-1",
        DeviceJobCreateRequest(device_id=registration.id, type=DeviceJobType.FIND_SYMBOL, payload={"name_path": "health", "relative_path": "src/api/routes.py"}),
    )
    assert job.status == DeviceJobStatus.PENDING_APPROVAL
    assert (await store.sync_device(project.id, registration.id, DeviceSyncRequest())).jobs == []

    approved = await store.approve_device_job(project.id, job.id, "owner-1", approved=True)
    assert approved is not None and approved.status == DeviceJobStatus.QUEUED
    delivery_sync = await store.sync_device(project.id, registration.id, DeviceSyncRequest())
    assert len(delivery_sync.jobs) == 1
    delivery = delivery_sync.jobs[0]
    assert delivery.id == job.id
    assert delivery.type == DeviceJobType.FIND_SYMBOL
    assert delivery.payload == {"name_path": "health", "relative_path": "src/api/routes.py"}

    result_sync = await store.sync_device(
        project.id,
        registration.id,
        DeviceSyncRequest(
            job_results=[
                DeviceJobResultSubmission(
                    job_id=job.id,
                    lease_id=delivery.lease_id,
                    status=DeviceJobStatus.COMPLETED,
                    result={"symbols": [{"name_path": "health", "kind": "function"}]},
                )
            ]
        ),
    )
    assert result_sync.accepted_job_result_ids == [job.id]
    completed = (await store.list_device_jobs(project.id))[0]
    assert completed.status == DeviceJobStatus.COMPLETED
    assert completed.result == {"symbols": [{"name_path": "health", "kind": "function"}]}

    replay = await store.sync_device(
        project.id,
        registration.id,
        DeviceSyncRequest(job_results=[DeviceJobResultSubmission(job_id=job.id, lease_id=delivery.lease_id, status=DeviceJobStatus.COMPLETED)]),
    )
    assert replay.accepted_job_result_ids == []
    assert replay.conflicts[0].code == "job_lease_invalid"


@pytest.mark.asyncio
async def test_device_pairing_and_sync_api(monkeypatch, tmp_path):
    from httpx import ASGITransport, AsyncClient

    from src.api import routes
    from src.config import Settings
    from src.main import app

    repository = create_repository(tmp_path / "repository")
    run_store = SQLiteRunStore(str(tmp_path / "api-hybrid-state.db"))
    monkeypatch.setattr(routes, "get_run_store", lambda: run_store)
    monkeypatch.setattr(routes, "get_settings", lambda: Settings(workspace_root=str(repository)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        projects = await client.get("/v1/projects")
        project_id = projects.json()[0]["id"]
        indexed = await client.post(f"/v1/projects/{project_id}/index")
        modules = (await client.get(f"/v1/projects/{project_id}/workspace")).json()["modules"]
        module_id = next(item["id"] for item in modules if item["source_scope"] == "src/api")

        pairing = await client.post(f"/v1/projects/{project_id}/devices/pair", json={"name_hint": "CI laptop"})
        registration = await client.post(
            f"/v1/projects/{project_id}/devices/register",
            json={
                "pairing_token": pairing.json()["pairing_token"],
                "name": "CI laptop",
                "public_key": "ci-local-public-key-material",
                "capabilities": ["serena.read_only", "graphiti.local"],
                "inventory": {"branch": "main", "commit_sha": "b" * 40, "dirty": False, "tracked_files": 5},
            },
        )
        device = registration.json()
        sync = await client.post(
            f"/v1/projects/{project_id}/devices/{device['id']}/sync",
            headers={"X-Device-Token": device["device_token"]},
            json={
                "cursor": 0,
                "events": [
                    {
                        "event_id": "evt-api-offline-note",
                        "type": "note.created",
                        "entity_id": "note-api-offline",
                        "base_revision": 0,
                        "payload": {"module_id": module_id, "title": "API offline note", "content": "This survives a local disconnect."},
                        "occurred_at": "2026-08-20T12:10:00+00:00",
                    }
                ],
            },
        )
        devices = await client.get(f"/v1/projects/{project_id}/devices")
        denied = await client.post(
            f"/v1/projects/{project_id}/devices/{device['id']}/sync",
            headers={"X-Device-Token": "invalid-device-token"},
            json={"cursor": 0, "events": []},
        )

    assert indexed.status_code == 200
    assert pairing.status_code == 201
    assert registration.status_code == 201
    assert sync.status_code == 200
    assert sync.json()["accepted_event_ids"] == ["evt-api-offline-note"]
    assert devices.status_code == 200
    assert devices.json()[0]["status"] == "online"
    assert denied.status_code == 401
    assert "device_token" not in devices.json()[0]


@pytest.mark.asyncio
async def test_paired_local_workspace_registry_and_source_selection(tmp_path):
    repository = create_repository(tmp_path / "repository")
    run_store = SQLiteRunStore(str(tmp_path / "workspace-source-state.db"))
    store = get_workspace_store(run_store)
    project = await store.ensure_default_project()
    pairing = await store.create_device_pairing(project.id, "owner-1", DevicePairingRequest(name_hint="Workspace laptop"))
    registration = await store.register_device(
        project.id,
        DeviceRegistrationRequest(
            pairing_token=pairing.pairing_token, name="Workspace laptop", public_key="workspace-local-public-key-material",
            inventory=LocalRepositoryInventory(repository_url="https://github.com/example/large.git", branch="main", commit_sha="e" * 40, tracked_files=200_000),
        ),
    )
    manifest = LocalWorkspaceManifest(
        workspace_key="a" * 64, display_name="large-project",
        inventory=LocalRepositoryInventory(repository_url="https://github.com/example/large.git", branch="main", commit_sha="e" * 40, tracked_files=200_000),
        index_revision=1, indexed_at="2026-08-20T14:00:00+00:00",
    )
    workspace = await store.upsert_local_workspace(project.id, registration.id, manifest)
    assert workspace.display_name == "large-project"
    assert workspace.workspace_key == "a" * 64
    assert str(repository) not in workspace.model_dump_json()

    local_source = await store.select_project_source(project.id, "owner-1", ProjectSourceSelectionRequest(kind=ProjectSourceKind.PAIRED_LOCAL, local_workspace_id=workspace.id))
    assert local_source.kind == ProjectSourceKind.PAIRED_LOCAL
    assert local_source.local_workspace_id == workspace.id
    github_source = await store.select_project_source(project.id, "owner-1", ProjectSourceSelectionRequest(kind=ProjectSourceKind.GITHUB_REPOSITORY, repository_url="https://github.com/example/large.git", ref="main"))
    assert github_source.kind == ProjectSourceKind.GITHUB_REPOSITORY
    assert github_source.repository_url == "https://github.com/example/large.git"


@pytest.mark.asyncio
async def test_device_job_api_requires_explicit_approval_before_sync_delivery(monkeypatch, tmp_path):
    from httpx import ASGITransport, AsyncClient

    from src.api import routes
    from src.config import Settings
    from src.main import app

    repository = create_repository(tmp_path / "repository")
    run_store = SQLiteRunStore(str(tmp_path / "device-job-api-state.db"))
    monkeypatch.setattr(routes, "get_run_store", lambda: run_store)
    monkeypatch.setattr(routes, "get_settings", lambda: Settings(workspace_root=str(repository)))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        projects = await client.get("/v1/projects")
        project_id = projects.json()[0]["id"]
        pairing = await client.post(f"/v1/projects/{project_id}/devices/pair", json={"name_hint": "Relay laptop"})
        registration = await client.post(
            f"/v1/projects/{project_id}/devices/register",
            json={
                "pairing_token": pairing.json()["pairing_token"], "name": "Relay laptop", "public_key": "relay-local-public-key-material",
                "capabilities": ["serena.read_only", "graphiti.local"], "inventory": {"branch": "main", "commit_sha": "d" * 40, "dirty": False, "tracked_files": 5},
            },
        )
        device = registration.json()
        created = await client.post(
            f"/v1/projects/{project_id}/devices/jobs",
            json={"device_id": device["id"], "type": "index_workspace", "payload": {}},
        )
        job = created.json()
        before_approval = await client.post(
            f"/v1/projects/{project_id}/devices/{device['id']}/sync", headers={"X-Device-Token": device["device_token"]}, json={"cursor": 0, "events": []},
        )
        approved = await client.post(f"/v1/projects/{project_id}/devices/jobs/{job['id']}/approval", json={"approved": True})
        delivered = await client.post(
            f"/v1/projects/{project_id}/devices/{device['id']}/sync", headers={"X-Device-Token": device["device_token"]}, json={"cursor": 0, "events": []},
        )

    assert created.status_code == 201
    assert job["status"] == "pending_approval"
    assert before_approval.status_code == 200 and before_approval.json()["jobs"] == []
    assert approved.status_code == 200 and approved.json()["status"] == "queued"
    assert delivered.status_code == 200 and delivered.json()["jobs"][0]["id"] == job["id"]
    assert "lease_id" in delivered.json()["jobs"][0]
