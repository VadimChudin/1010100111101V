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
