from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .config import RuntimeConfig

REPOSITORY = "VadimChudin/1010100111101V"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/tags/runtime-latest"


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    schema: int
    version: str
    build: str
    asset_name: str
    asset_url: str
    sha256: str
    published_at: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReleaseManifest":
        required = {"schema", "version", "build", "asset_name", "asset_url", "sha256", "published_at"}
        missing = required.difference(payload)
        if missing:
            raise ValueError(f"Release manifest misses: {', '.join(sorted(missing))}")
        if int(payload["schema"]) != 1 or len(str(payload["sha256"])) != 64:
            raise ValueError("Release manifest is invalid")
        return cls(
            schema=int(payload["schema"]), version=str(payload["version"]), build=str(payload["build"]),
            asset_name=str(payload["asset_name"]), asset_url=str(payload["asset_url"]), sha256=str(payload["sha256"]),
            published_at=str(payload["published_at"]),
        )


class RuntimeUpdater:
    """Release-channel updater. It only accepts a checksum-verified wheel from runtime-latest."""

    def __init__(self, config: RuntimeConfig, release_api: str = LATEST_RELEASE_API) -> None:
        self.config = config
        self.release_api = release_api

    @property
    def updates_dir(self) -> Path:
        return Path(self.config.state_dir) / "updates"

    async def check(self) -> ReleaseManifest | None:
        async with httpx.AsyncClient(timeout=20, headers={"Accept": "application/vnd.github+json"}) as client:
            release_response = await client.get(self.release_api)
            if release_response.status_code == 404:
                return None
            release_response.raise_for_status()
            release = release_response.json()
            assets = {str(asset["name"]): str(asset["browser_download_url"]) for asset in release.get("assets", [])}
            manifest_url = assets.get("runtime-update.json")
            if not manifest_url:
                raise ValueError("runtime-latest release does not include runtime-update.json")
            manifest_response = await client.get(manifest_url)
            manifest_response.raise_for_status()
        manifest = ReleaseManifest.from_payload(manifest_response.json())
        if manifest.asset_name not in assets or assets[manifest.asset_name] != manifest.asset_url:
            raise ValueError("Release manifest asset does not match the published runtime-latest assets")
        return manifest

    async def stage(self, manifest: ReleaseManifest) -> Path:
        self.updates_dir.mkdir(parents=True, exist_ok=True)
        destination = self.updates_dir / manifest.asset_name
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(manifest.asset_url)
            response.raise_for_status()
            payload = response.content
        digest = hashlib.sha256(payload).hexdigest()
        if digest != manifest.sha256:
            raise ValueError("Downloaded update checksum does not match the release manifest")
        temporary = destination.with_suffix(f"{destination.suffix}.partial")
        temporary.write_bytes(payload)
        temporary.replace(destination)
        return destination

    def apply(self, manifest: ReleaseManifest, wheel_path: str | Path) -> None:
        path = Path(wheel_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != manifest.sha256:
            raise ValueError("Staged update checksum does not match the release manifest")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "--force-reinstall", str(path)],
            check=True,
        )
        self.config.runtime_version = manifest.version
        self.config.installed_build = manifest.build
        self.config.save()

    async def check_and_stage(self) -> tuple[ReleaseManifest | None, Path | None]:
        manifest = await self.check()
        if manifest is None or manifest.build == self.config.installed_build:
            return manifest, None
        return manifest, await self.stage(manifest)
