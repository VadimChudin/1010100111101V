#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="VadimChudin/1010100111101V"
RELEASE_API="https://api.github.com/repos/${REPOSITORY}/releases/tags/runtime-latest"
STATE_DIR="${AGENT_ROOM_HOME:-${HOME}/.agent-room}"
VENV_DIR="${STATE_DIR}/venv"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11+ is required. Install Python, then run this installer again." >&2
  exit 1
fi

mkdir -p "${STATE_DIR}/bootstrap"
MANIFEST="${STATE_DIR}/bootstrap/runtime-update.json"
WHEEL="${STATE_DIR}/bootstrap/agent_room_runtime-latest-py3-none-any.whl"

python3 - "${RELEASE_API}" "${MANIFEST}" "${WHEEL}" <<'PY'
import hashlib
import json
import sys
import urllib.request

release_api, manifest_path, wheel_path = sys.argv[1:]
headers = {"Accept": "application/vnd.github+json", "User-Agent": "agent-room-runtime-installer"}
request = urllib.request.Request(release_api, headers=headers)
with urllib.request.urlopen(request, timeout=30) as response:
    release = json.load(response)
assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
manifest_url = assets.get("runtime-update.json")
if not manifest_url:
    raise SystemExit("runtime-latest does not provide an update manifest")
with urllib.request.urlopen(urllib.request.Request(manifest_url, headers=headers), timeout=30) as response:
    manifest = json.load(response)
asset_name = manifest["asset_name"]
asset_url = manifest["asset_url"]
if assets.get(asset_name) != asset_url:
    raise SystemExit("manifest asset is not a published runtime-latest asset")
with urllib.request.urlopen(urllib.request.Request(asset_url, headers=headers), timeout=120) as response:
    payload = response.read()
digest = hashlib.sha256(payload).hexdigest()
if digest != manifest["sha256"]:
    raise SystemExit("runtime checksum verification failed")
open(manifest_path, "w", encoding="utf-8").write(json.dumps(manifest, indent=2) + "\n")
open(wheel_path, "wb").write(payload)
print(f"Verified Agent Room Runtime {manifest['version']} ({manifest['build'][:12]})")
PY

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check --upgrade "${WHEEL}"

cat <<EOF

Agent Room Runtime is installed in ${VENV_DIR}.

Next steps:
1. Create a one-time pairing token in the Agent Room dashboard.
2. Initialize this PC:
   ${VENV_DIR}/bin/agent-room-runtime init --cloud-url https://app-production-cc16.up.railway.app --project-id default --workspace-root /absolute/path/to/project --state-dir ${STATE_DIR}/default --device-name "$(hostname)"
3. Register the pairing token, then start sync:
   ${VENV_DIR}/bin/agent-room-runtime register --config ${STATE_DIR}/default/runtime.json --pairing-token <token>
   ${VENV_DIR}/bin/agent-room-runtime serve --config ${STATE_DIR}/default/runtime.json --auto-update
EOF
