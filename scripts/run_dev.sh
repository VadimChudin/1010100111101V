#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
exec uvicorn src.main:app --reload --host 0.0.0.0 --port "${PORT:-8000}"
