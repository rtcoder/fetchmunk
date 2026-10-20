#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
backend/.venv/bin/python -m PyInstaller --noconfirm --clean packaging/backend.spec
