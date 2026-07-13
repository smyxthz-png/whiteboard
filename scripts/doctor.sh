#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT/.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="${PYTHON:-python3}"

cd "$ROOT"
"$PYTHON_BIN" "$ROOT/scripts/doctor.py"
