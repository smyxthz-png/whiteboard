# Auto Whiteboard Video

Use this skill when the user wants to generate a narrated whiteboard video from a text file or pasted transcript.

## Before Running

The repository must be bootstrapped and configured:

```bash
python scripts/configure_keys.py
python scripts/doctor.py
```

The local files below must exist and contain real user-provided keys:

- `auto-whiteboard/config/config.ini`
- `skills/whiteboard-video-workflow/.env`

## Command

From the repository root:

```bash
skills/auto-whiteboard-video/skill.sh examples/demo_30s.txt --output-dir output/demo --project-dir output/demo/latest --keep-temp
```

The skill delegates to:

```bash
python auto-whiteboard/scripts/auto_generate.py
```

## Defaults

- TTS: MiniMax/302
- Image provider: configured in `skills/whiteboard-video-workflow/.env`
- BGM: configured in `auto-whiteboard/config/config.ini`
- Subtitle display normalization: enabled by the main workflow

## Output

The final result is:

```text
<project-dir>/final_video.mp4
<project-dir>/composition_report.json
```

Report the final video path and the validation metrics from `composition_report.json`.
