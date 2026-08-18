#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
if [[ ! -f .env ]]; then cp .env.example .env; fi
echo 'Setup complete. Edit .env and run: bash scripts/run_dev.sh'
