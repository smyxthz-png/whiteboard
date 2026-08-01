---
name: auto-whiteboard-video
description: Generate a complete narrated whiteboard explainer video from a UTF-8 transcript. Use when the user asks to turn pasted text or a .txt script into a whiteboard video with TTS, subtitles, generated illustrations, hand-drawing animation, BGM, and a final 1920x1080 MP4.
---

# Auto Whiteboard Video

Use the repository's canonical pipeline. Do not rebuild stages manually unless troubleshooting a failed stage.

## Workflow

1. Run `scripts/doctor.py` from the repository root.
2. Save pasted text as a UTF-8 `.txt` file under a user-approved input location when no file is provided.
3. Choose a stable project directory under `output/`; reuse it when resuming.
4. Run the wrapper below and wait for completion.
5. Read `composition_report.json` and report the final MP4 path, resolution, duration, and audio/video delta.

```powershell
python skills/auto-whiteboard-video/scripts/run_video.py `
  --input examples/demo_30s.txt `
  --output-dir output/demo `
  --project-dir output/demo/latest `
  --keep-temp
```

All arguments are forwarded to `auto-whiteboard/scripts/auto_generate.py`.

## Locked Defaults

- Output: `1920x1080`, 30 fps.
- Source images: near 16:9; reject clear 3:2, square, and portrait results.
- Visual style: `#F6F1E3` background, black marker lines, restrained amber, faceless round-headed people.
- Subtitles: size 88, maximum 20 full-width CJK characters per line.
- BGM: configured default track at `-28 dB`.
- Spoken numbers and display subtitles are normalized separately.

## Resume Rules

- Reuse the same `--project-dir` to preserve caches.
- Use `--force-tts`, `--force-images`, `--force-whiteboard`, or `--force-compose` only when that stage must change.
- Do not delete the project directory to fix a single failed scene.

## Success Criteria

Require both `final_video.mp4` and `composition_report.json`. Confirm `1920x1080`, single-line subtitles, and `output_av_delta_seconds < 0.1` before reporting success.
