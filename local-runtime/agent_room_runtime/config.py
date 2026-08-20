from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class RuntimeConfig:
    cloud_url: str
    project_id: str
    workspace_root: str
    state_dir: str
    device_id: str = ""
    device_token: str = ""
    workspace_id: str = ""
    device_name: str = "Local Agent Room Runtime"
    runtime_version: str = "0.1.0"
    installed_build: str = "source"
    public_key: str = ""

    @property
    def config_path(self) -> Path:
        return Path(self.state_dir) / "runtime.json"

    @property
    def database_path(self) -> Path:
        return Path(self.state_dir) / "runtime.db"

    @property
    def is_registered(self) -> bool:
        return bool(self.device_id and self.device_token)

    @classmethod
    def load(cls, path: str | Path) -> "RuntimeConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**payload)

    def save(self) -> None:
        path = self.config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")
