from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY = "VadimChudin/1010100111101V"
RELEASE_TAG = "runtime-latest"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare verified Agent Room runtime release assets")
    parser.add_argument("--dist", default="dist")
    parser.add_argument("--output", default="release")
    parser.add_argument("--build", required=True)
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    dist = (root / arguments.dist).resolve()
    output = (root / arguments.output).resolve()
    wheels = sorted(dist.glob("agent_room_runtime-*.whl"))
    wheel = wheels[0] if wheels else None
    if wheel is None:
        raise SystemExit("No runtime wheel found. Build the package first.")
    with (root / "pyproject.toml").open("rb") as handle:
        version = str(tomllib.load(handle)["project"]["version"])

    output.mkdir(parents=True, exist_ok=True)
    asset_name = wheel.name
    published_wheel = output / asset_name
    shutil.copy2(wheel, published_wheel)
    digest = sha256(published_wheel)
    asset_url = f"https://github.com/{REPOSITORY}/releases/download/{RELEASE_TAG}/{asset_name}"
    manifest = {
        "schema": 1,
        "version": version,
        "build": arguments.build,
        "asset_name": asset_name,
        "asset_url": asset_url,
        "sha256": digest,
        "published_at": os.getenv("RELEASE_PUBLISHED_AT", datetime.now(UTC).isoformat()),
    }
    (output / "runtime-update.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text(f"{digest}  {asset_name}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
