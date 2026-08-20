from __future__ import annotations

import asyncio
import hashlib
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .config import RuntimeConfig
from .outbox import LocalOutbox


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def git_inventory(workspace_root: str | Path) -> dict[str, Any]:
    root = Path(workspace_root).resolve()

    def run(*arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20
        )
        return completed.stdout.strip()

    try:
        repository_url = run("config", "--get", "remote.origin.url") or "local"
        branch = run("rev-parse", "--abbrev-ref", "HEAD")
        commit_sha = run("rev-parse", "HEAD")
        dirty = bool(run("status", "--porcelain"))
        files = [path for path in run("ls-files").splitlines() if path]
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("workspace_root must be a readable Git repository") from exc
    fingerprint = hashlib.sha256("\n".join([repository_url, branch, commit_sha, *files]).encode("utf-8")).hexdigest()
    return {
        "repository_url": repository_url,
        "branch": branch,
        "commit_sha": commit_sha,
        "dirty": dirty,
        "tracked_files": len(files),
        "workspace_fingerprint": fingerprint,
    }


class LocalRuntime:
    """PC-side runtime. It never exposes an inbound listener or raw shell API."""

    capabilities = ["serena.read_only", "graphiti.local", "git.inventory", "project.event_sync"]

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.outbox = LocalOutbox(config.database_path)
        self.outbox.initialize()

    @property
    def base_url(self) -> str:
        return self.config.cloud_url.rstrip("/")

    async def register(self, pairing_token: str) -> dict[str, Any]:
        inventory = git_inventory(self.config.workspace_root)
        public_key = self.config.public_key or secrets.token_urlsafe(32)
        payload = {
            "pairing_token": pairing_token,
            "name": self.config.device_name,
            "runtime_version": self.config.runtime_version,
            "public_key": public_key,
            "capabilities": self.capabilities,
            "inventory": inventory,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self.base_url}/v1/projects/{self.config.project_id}/devices/register", json=payload)
            response.raise_for_status()
            registration = response.json()
        self.config.device_id = str(registration["id"])
        self.config.device_token = str(registration["device_token"])
        self.config.public_key = public_key
        self.config.save()
        return registration

    def enqueue(self, event: dict[str, Any]) -> None:
        self.outbox.enqueue(event, iso_now())

    async def sync_once(self) -> dict[str, Any]:
        if not self.config.is_registered:
            raise RuntimeError("Runtime is not paired. Run the register command first.")
        payload = {
            "cursor": self.outbox.cursor(),
            "events": self.outbox.pending(),
            "inventory": git_inventory(self.config.workspace_root),
        }
        headers = {"X-Device-Token": self.config.device_token}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/v1/projects/{self.config.project_id}/devices/{self.config.device_id}/sync",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
        self.outbox.acknowledge(list(result.get("accepted_event_ids", [])), iso_now())
        self.outbox.apply_server_events(list(result.get("events", [])), int(result["server_cursor"]), iso_now())
        return result

    async def sync_forever(self, interval_seconds: float = 10.0, max_backoff_seconds: float = 60.0) -> None:
        """Run under a local service manager; failures retain outbox data and retry safely."""
        delay = max(1.0, interval_seconds)
        while True:
            try:
                await self.sync_once()
                delay = max(1.0, interval_seconds)
            except (httpx.HTTPError, RuntimeError):
                delay = min(max_backoff_seconds, delay * 2)
            await asyncio.sleep(delay)
