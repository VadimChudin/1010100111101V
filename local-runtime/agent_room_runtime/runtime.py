from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from time import monotonic

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
            "job_results": self.outbox.pending_job_results(),
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
        timestamp = iso_now()
        self.outbox.acknowledge(list(result.get("accepted_event_ids", [])), timestamp)
        accepted_job_ids = list(result.get("accepted_job_result_ids", []))
        rejected_job_ids = [
            str(conflict.get("event_id"))
            for conflict in list(result.get("conflicts", []))
            if str(conflict.get("code", "")).startswith("job_") and conflict.get("event_id")
        ]
        self.outbox.acknowledge_job_results(accepted_job_ids + rejected_job_ids, timestamp)
        self.outbox.apply_server_events(list(result.get("events", [])), int(result["server_cursor"]), timestamp)
        if result.get("jobs"):
            from .jobs import DeviceJobExecutor

            executor = DeviceJobExecutor(self)
            for job in list(result["jobs"]):
                job_id = str(job["id"])
                lease_id = str(job["lease_id"])
                try:
                    job_result = await executor.execute(job)
                    submission = {"job_id": job_id, "lease_id": lease_id, "status": "completed", "result": job_result}
                except (OSError, RuntimeError, ValueError, PermissionError, httpx.HTTPError) as exc:
                    submission = {"job_id": job_id, "lease_id": lease_id, "status": "failed", "result": {}, "error": str(exc)[:2000]}
                self.outbox.enqueue_job_result(job_id, lease_id, submission, iso_now())
        return result

    async def sync_forever(
        self,
        interval_seconds: float = 10.0,
        max_backoff_seconds: float = 60.0,
        *,
        auto_update: bool = False,
        update_interval_seconds: float = 3600.0,
    ) -> None:
        """Run under a local service manager; failures retain outbox data and retry safely."""
        delay = max(1.0, interval_seconds)
        next_update_check = 0.0
        while True:
            try:
                await self.sync_once()
                delay = max(1.0, interval_seconds)
            except (httpx.HTTPError, RuntimeError):
                delay = min(max_backoff_seconds, delay * 2)
            if auto_update and monotonic() >= next_update_check:
                next_update_check = monotonic() + max(300.0, update_interval_seconds)
                try:
                    from .updates import RuntimeUpdater

                    manifest, staged = await RuntimeUpdater(self.config).check_and_stage()
                    if manifest is not None and staged is not None:
                        RuntimeUpdater(self.config).apply(manifest, staged)
                        os.execv(
                            os.sys.executable,
                            [os.sys.executable, "-m", "agent_room_runtime.cli", "serve", "--config", str(self.config.config_path), "--auto-update"],
                        )
                except (httpx.HTTPError, OSError, RuntimeError, ValueError):
                    # Updates never block sync or erase a durable outbox; retry on the next update interval.
                    pass
            await asyncio.sleep(delay)
