# Auto Whiteboard Core Workflow

This folder contains the main Python workflow.

Prefer the repository-level agent scripts:

```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\python.exe scripts\configure_keys.py
.\scripts\doctor.ps1
.\scripts\run_demo.ps1
```

Manual command from repository root:

```bash
python auto-whiteboard/scripts/auto_generate.py \
  --input examples/demo_30s.txt \
  --output-dir output/demo \
  --project-dir output/demo/latest \
  --bgm skills/whiteboard-animation/assets/bgm/relaxing-piano-for-sleeping-312507.mp3 \
  --bgm-volume -28 \
  --tts-concurrency 16 \
  --whiteboard-jobs 4 \
  --keep-temp
```

## Configuration

Local config file:

```text
auto-whiteboard/config/config.ini
```

Create it from:

```text
auto-whiteboard/config/config.example.ini
```

The easiest path is:

```bash
python scripts/configure_keys.py
```

## Output

The final project directory contains:

- `final_video.mp4`
- `voiceover.wav`
- `subtitles.srt`
- `composition_report.json`
- `run_state.json`

The workflow supports resuming/reusing steps through `run_state.json`.
