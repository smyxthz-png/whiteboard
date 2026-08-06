#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -n "${PYTHON:-}" ]; then
  PYTHON_BIN="$PYTHON"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="python3.12"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="python3.11"
else
  PYTHON_BIN="python3"
fi
VENV="$ROOT/.venv"
VENV_PYTHON="$VENV/bin/python"

cd "$ROOT"

if [ -x /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg ]; then
  export PATH="/opt/homebrew/opt/ffmpeg-full/bin:$PATH"
fi

echo "[1/6] Checking Python..."
"$PYTHON_BIN" --version

if [ ! -x "$VENV_PYTHON" ]; then
  echo "[2/6] Creating root virtual environment..."
  "$PYTHON_BIN" -m venv "$VENV"
else
  echo "[2/6] Root virtual environment exists."
fi

echo "[3/6] Installing Python dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$ROOT/auto-whiteboard/requirements.txt"

echo "[4/6] Preparing local config files..."
[ -f "$ROOT/auto-whiteboard/config/config.ini" ] || cp "$ROOT/auto-whiteboard/config/config.example.ini" "$ROOT/auto-whiteboard/config/config.ini"
[ -f "$ROOT/skills/whiteboard-video-workflow/.env" ] || cp "$ROOT/skills/whiteboard-video-workflow/.env.example" "$ROOT/skills/whiteboard-video-workflow/.env"

echo "[5/6] Preparing whiteboard animation environment..."
"$VENV_PYTHON" "$ROOT/skills/whiteboard-animation/scripts/setup_env.py"

echo "[6/6] Checking ffmpeg..."
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  echo "[OK] ffmpeg and ffprobe found."
else
  echo "[WARN] ffmpeg/ffprobe is missing. Install ffmpeg, then run bash scripts/doctor.sh."
fi

echo ""
echo "[OK] Bootstrap complete."
echo "Next:"
echo "  ./.venv/bin/python scripts/configure_keys.py"
echo "  bash scripts/doctor.sh"
echo "  bash scripts/run_demo.sh"
