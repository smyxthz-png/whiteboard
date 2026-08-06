#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT/.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="${PYTHON:-python3}"

# Homebrew's regular ffmpeg may omit libass. Prefer the keg-only full build
# when it is installed so final subtitle burn-in works without manual PATH edits.
if [ -x /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg ]; then
  export PATH="/opt/homebrew/opt/ffmpeg-full/bin:$PATH"
fi

INPUT_FILE="${1:-examples/demo_30s.txt}"
PROJECT_DIR="${PROJECT_DIR:-output/demo/latest}"
TTS_CONCURRENCY="${TTS_CONCURRENCY:-16}"
WHITEBOARD_JOBS="${WHITEBOARD_JOBS:-4}"

cd "$ROOT"
"$PYTHON_BIN" "auto-whiteboard/scripts/auto_generate.py" \
  --input "$INPUT_FILE" \
  --output-dir "output/demo" \
  --project-dir "$PROJECT_DIR" \
  --bgm "skills/whiteboard-animation/assets/bgm/relaxing-piano-for-sleeping-312507.mp3" \
  --bgm-volume -28 \
  --tts-concurrency "$TTS_CONCURRENCY" \
  --whiteboard-jobs "$WHITEBOARD_JOBS" \
  --keep-temp \
  --force-compose
