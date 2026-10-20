#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Developer tooling only. End users receive the frozen runtime inside the app.
uv python install 3.13.16 --install-dir build/python
PYTHON="$ROOT/build/python/cpython-3.13.16-macos-aarch64-none/bin/python3.13"
uv venv --python "$PYTHON" backend/.venv
uv pip sync --python backend/.venv/bin/python --require-hashes backend/requirements.lock
