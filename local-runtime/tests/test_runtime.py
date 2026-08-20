from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_room_runtime.outbox import LocalOutbox
from agent_room_runtime.serena import SerenaLaunchSpec, validate_tool


def test_outbox_persists_queue_and_server_cursor(tmp_path):
    outbox = LocalOutbox(tmp_path / "runtime.db")
    outbox.initialize()
    event = {"event_id": "evt-1", "type": "note.created", "entity_id": "note-1"}
    outbox.enqueue(event, "2026-08-20T12:00:00+00:00")
    outbox.enqueue(event, "2026-08-20T12:00:01+00:00")

    assert outbox.pending() == [event]
    outbox.acknowledge(["evt-1"], "2026-08-20T12:00:02+00:00")
    assert outbox.pending() == []

    cloud_event = {"sequence": 7, "event_id": "evt-cloud", "type": "graphiti.episode", "entity_id": "episode-1"}
    outbox.apply_server_events([cloud_event], 7, "2026-08-20T12:00:03+00:00")
    outbox.apply_server_events([cloud_event], 7, "2026-08-20T12:00:04+00:00")
    assert outbox.cursor() == 7
    assert outbox.received() == [cloud_event]


def test_serena_policy_binds_to_loopback_and_read_only_tools(tmp_path):
    command = SerenaLaunchSpec(str(tmp_path / "workspace"), port=9240).command()
    assert command[:5] == ["serena", "start-mcp-server", "--transport", "streamable-http", "--host"]
    assert "127.0.0.1" in command
    assert "--open-web-dashboard" in command
    assert validate_tool("find_symbol") == "find_symbol"
    with pytest.raises(PermissionError):
        validate_tool("execute_shell_command")


@pytest.mark.asyncio
async def test_graphiti_memory_enqueues_provenance_episode(tmp_path):
    from agent_room_runtime.config import RuntimeConfig
    from agent_room_runtime.graphiti import LocalGraphitiMemory
    from agent_room_runtime.runtime import LocalRuntime

    config = RuntimeConfig(
        cloud_url="https://cloud.example",
        project_id="project-1",
        workspace_root=str(tmp_path),
        state_dir=str(tmp_path / "state"),
    )
    runtime = LocalRuntime(config)
    episode_id = await LocalGraphitiMemory(runtime).add_episode(
        "Decision", "Keep Serena local and replay Graphiti provenance after reconnect.", source_commit_sha="a" * 40
    )
    pending = runtime.outbox.pending()
    assert pending[0]["entity_id"] == episode_id
    assert pending[0]["type"] == "graphiti.episode"
    assert pending[0]["payload"]["group_id"] == "project-1"


def test_release_manifest_rejects_incomplete_or_invalid_payloads():
    from agent_room_runtime.updates import ReleaseManifest

    with pytest.raises(ValueError):
        ReleaseManifest.from_payload({"schema": 1})
    with pytest.raises(ValueError):
        ReleaseManifest.from_payload({
            "schema": 2, "version": "0.1.0", "build": "abc", "asset_name": "runtime.whl", "asset_url": "https://example/runtime.whl",
            "sha256": "a" * 64, "published_at": "2026-08-20T12:00:00+00:00",
        })


def test_verified_apply_preserves_pairing_and_records_release(monkeypatch, tmp_path):
    from agent_room_runtime.config import RuntimeConfig
    from agent_room_runtime.updates import ReleaseManifest, RuntimeUpdater

    wheel = tmp_path / "agent_room_runtime-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"verified-wheel")
    import hashlib
    manifest = ReleaseManifest(
        schema=1, version="0.1.0", build="build-123", asset_name=wheel.name, asset_url="https://example/runtime.whl",
        sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(), published_at="2026-08-20T12:00:00+00:00",
    )
    config = RuntimeConfig(
        cloud_url="https://cloud.example", project_id="project-1", workspace_root=str(tmp_path), state_dir=str(tmp_path / "state"),
        device_id="paired-device", device_token="opaque-device-token",
    )
    calls = []
    monkeypatch.setattr("agent_room_runtime.updates.subprocess.run", lambda command, check: calls.append((command, check)))

    RuntimeUpdater(config).apply(manifest, wheel)

    assert calls and "--force-reinstall" in calls[0][0]
    assert config.installed_build == "build-123"
    assert config.device_id == "paired-device"
    assert config.device_token == "opaque-device-token"
    assert config.config_path.is_file()


def test_outbox_persists_job_results_until_cloud_acknowledgement(tmp_path):
    outbox = LocalOutbox(tmp_path / "runtime.db")
    outbox.initialize()
    payload = {"job_id": "job-1", "lease_id": "lease-1234567890123456", "status": "completed", "result": {"symbols": []}}
    outbox.enqueue_job_result("job-1", "lease-1234567890123456", payload, "2026-08-20T12:00:00+00:00")
    outbox.enqueue_job_result("job-1", "lease-1234567890123456", {"status": "failed"}, "2026-08-20T12:01:00+00:00")
    assert outbox.pending_job_results() == [payload]
    outbox.acknowledge_job_results(["job-1"], "2026-08-20T12:02:00+00:00")
    assert outbox.pending_job_results() == []


@pytest.mark.asyncio
async def test_device_job_executor_uses_only_matching_typed_read_only_serena_job(tmp_path):
    from agent_room_runtime.config import RuntimeConfig
    from agent_room_runtime.jobs import DeviceJobExecutor
    from agent_room_runtime.runtime import LocalRuntime

    class FakeSerena:
        async def call(self, tool_name, arguments):
            assert tool_name == "find_symbol"
            assert arguments == {"name_path": "health", "relative_path": "src/api/routes.py"}
            return {"content": [{"type": "text", "text": "symbol result"}]}

    config = RuntimeConfig(
        cloud_url="https://cloud.example", project_id="project-1", workspace_root=str(tmp_path), state_dir=str(tmp_path / "state"),
        device_id="device-1", device_token="opaque-device-token",
    )
    executor = DeviceJobExecutor(LocalRuntime(config), serena=FakeSerena())
    result = await executor.execute(
        {
            "id": "job-1", "project_id": "project-1", "device_id": "device-1", "type": "find_symbol",
            "payload": {"name_path": "health", "relative_path": "src/api/routes.py"}, "lease_id": "lease-1234567890123456",
        }
    )
    assert result["tool"] == "find_symbol"
    with pytest.raises(PermissionError):
        await executor.execute({"project_id": "other-project", "device_id": "device-1", "type": "find_symbol", "payload": {}})
    with pytest.raises(PermissionError):
        await executor.execute({"project_id": "project-1", "device_id": "device-1", "type": "execute_shell", "payload": {}})


def _create_scoped_workspace(path: Path) -> Path:
    import subprocess

    path.mkdir()
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    (path / ".env").write_text("TOP_SECRET=never-expose\n", encoding="utf-8")
    (path / "agent-room.toml").write_text("[tests.version]\ncommand = [\"python\", \"--version\"]\ntimeout_seconds = 30\n", encoding="utf-8")
    for command in (["git", "init", "--quiet"], ["git", "config", "user.email", "test@example.com"], ["git", "config", "user.name", "Test"], ["git", "add", "src", "agent-room.toml"], ["git", "commit", "--quiet", "-m", "initial"]):
        subprocess.run(command, cwd=path, check=True)
    return path


def test_local_workspace_executor_enforces_boundary_and_typed_operations(tmp_path):
    from agent_room_runtime.workspace_ops import LocalWorkspaceExecutor, WorkspaceBoundaryError

    workspace = _create_scoped_workspace(tmp_path / "workspace")
    executor = LocalWorkspaceExecutor(workspace)
    index = executor.refresh_index()
    assert index["content_uploaded"] is False
    assert "src/app.py" in executor.list_files()["files"]
    assert executor.search_text("value")["matches"] == ["src/app.py:1:value = 1"]
    assert executor.read_file_range("src/app.py", 1, 10)["lines"] == ["value = 1"]
    with pytest.raises(WorkspaceBoundaryError):
        executor.read_file_range(".env", 1, 1)

    patch = "--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"
    applied = executor.apply_unified_patch(patch)
    assert applied["applied"] is True
    assert executor.read_file_range("src/app.py", 1, 1)["lines"] == ["value = 2"]
    assert executor.run_test_profile("version")["exit_code"] == 0


def test_release_manifest_uses_the_canonical_versioned_wheel_filename(monkeypatch, tmp_path):
    import importlib.util
    import json
    import sys
    from pathlib import Path

    script = Path(__file__).parents[1] / "scripts" / "build_release_manifest.py"
    specification = importlib.util.spec_from_file_location("build_release_manifest", script)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

    dist = tmp_path / "dist"
    release = tmp_path / "release"
    dist.mkdir()
    wheel = dist / "agent_room_runtime-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"valid-versioned-wheel")
    monkeypatch.setattr(sys, "argv", [str(script), "--dist", str(dist), "--output", str(release), "--build", "build-123"])

    module.main()

    manifest = json.loads((release / "runtime-update.json").read_text(encoding="utf-8"))
    assert manifest["asset_name"] == wheel.name
    assert "-latest-" not in manifest["asset_name"]
    assert (release / wheel.name).is_file()
