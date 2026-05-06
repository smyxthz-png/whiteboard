#!/bin/bash
# Auto Whiteboard Video Generator Skill Entry Point

set -e

# Get the skill directory
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SKILL_DIR/../.." && pwd)"

# Parse arguments
INPUT_FILE=""
TEXT_CONTENT=""
OUTPUT_DIR=""
BGM=""
KEEP_TEMP=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --text)
            TEXT_CONTENT="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --bgm)
            BGM="$2"
            shift 2
            ;;
        --keep-temp)
            KEEP_TEMP="--keep-temp"
            shift
            ;;
        *)
            INPUT_FILE="$1"
            shift
            ;;
    esac
done

# Create temp file if text content provided
if [ -n "$TEXT_CONTENT" ]; then
    TEMP_FILE="$(mktemp --suffix=.txt)"
    echo "$TEXT_CONTENT" > "$TEMP_FILE"
    INPUT_FILE="$TEMP_FILE"
    trap "rm -f $TEMP_FILE" EXIT
fi

# Validate input
if [ -z "$INPUT_FILE" ]; then
    echo "Error: No input file or text content provided"
    echo "Usage: /auto-whiteboard-video <file> or /auto-whiteboard-video --text \"content\""
    exit 1
fi

# Build command
CMD="py -3.12 \"$PROJECT_ROOT/auto-whiteboard/scripts/auto_generate.py\" --input \"$INPUT_FILE\""

if [ -n "$OUTPUT_DIR" ]; then
    CMD="$CMD --output-dir \"$OUTPUT_DIR\""
fi

if [ -n "$BGM" ]; then
    CMD="$CMD --bgm \"$BGM\""
fi

if [ -n "$KEEP_TEMP" ]; then
    CMD="$CMD $KEEP_TEMP"
fi

CMD="$CMD --config \"$PROJECT_ROOT/auto-whiteboard/config/config.ini\""

# Execute
echo "Starting auto whiteboard video generation..."
eval $CMD
