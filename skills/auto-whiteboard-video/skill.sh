#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SKILL_DIR/../.." && pwd)"

INPUT_FILE=""
TEXT_CONTENT=""
OUTPUT_DIR=""
PROJECT_DIR=""
KEEP_TEMP=""
TTS_CONCURRENCY="16"
WHITEBOARD_JOBS="4"
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --text)
      TEXT_CONTENT="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --project-dir)
      PROJECT_DIR="$2"
      shift 2
      ;;
    --tts-concurrency)
      TTS_CONCURRENCY="$2"
      shift 2
      ;;
    --whiteboard-jobs)
      WHITEBOARD_JOBS="$2"
      shift 2
      ;;
    --keep-temp)
      KEEP_TEMP="--keep-temp"
      shift
      ;;
    --force-tts|--force-split|--force-images|--force-whiteboard|--force-compose)
      EXTRA_ARGS+=("$1")
      shift
      ;;
    *)
      if [[ -z "$INPUT_FILE" ]]; then
        INPUT_FILE="$1"
      else
        EXTRA_ARGS+=("$1")
      fi
      shift
      ;;
  esac
done

if [[ -n "$TEXT_CONTENT" ]]; then
  TEMP_FILE="$(mktemp "${TMPDIR:-/tmp}/whiteboard-text.XXXXXX.txt")"
  printf "%s\n" "$TEXT_CONTENT" > "$TEMP_FILE"
  INPUT_FILE="$TEMP_FILE"
  trap 'rm -f "$TEMP_FILE"' EXIT
fi

if [[ -z "$INPUT_FILE" ]]; then
  echo "Usage: skill.sh <input.txt> [--output-dir DIR] [--project-dir DIR] [--text TEXT]" >&2
  exit 1
fi

PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON:-python3}"
fi

CMD=(
  "$PYTHON_BIN"
  "$PROJECT_ROOT/auto-whiteboard/scripts/auto_generate.py"
  --input "$INPUT_FILE"
  --config "$PROJECT_ROOT/auto-whiteboard/config/config.ini"
  --tts-concurrency "$TTS_CONCURRENCY"
  --whiteboard-jobs "$WHITEBOARD_JOBS"
)

if [[ -n "$OUTPUT_DIR" ]]; then
  CMD+=(--output-dir "$OUTPUT_DIR")
fi
if [[ -n "$PROJECT_DIR" ]]; then
  CMD+=(--project-dir "$PROJECT_DIR")
fi
if [[ -n "$KEEP_TEMP" ]]; then
  CMD+=("$KEEP_TEMP")
fi
CMD+=("${EXTRA_ARGS[@]}")

cd "$PROJECT_ROOT"
echo "Starting whiteboard video generation..."
"${CMD[@]}"
