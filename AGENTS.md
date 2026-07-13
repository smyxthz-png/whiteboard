# Agent Install Guide

This repository is designed so an AI coding agent can install and run it for a user.

Use this file first. Ignore older garbled quickstart files if they conflict with this guide.

## Goal

Install the whiteboard video workflow, ask the user only for required API keys, run a short demo, and report the final video path.

## Required User Secrets

Ask the user for:

- MiniMax or 302.ai API key for TTS
- One image API key for a `gpt-image-2` provider

Supported image providers:

- `apimart_image2`
- `kie_image2`
- `t8_image2`
- `macode_image2`

Do not ask for a Claude key unless the user wants AI text splitting. The default demo uses rule-based splitting.

## Recommended Agent Flow

1. Inspect the repository root.
2. Run bootstrap:
   - Windows PowerShell: `.\scripts\bootstrap.ps1`
   - macOS/Linux: `bash scripts/bootstrap.sh`
3. Configure keys:
   - Interactive: `python scripts/configure_keys.py`
   - Non-interactive example:
     `python scripts/configure_keys.py --tts-key <KEY> --image-provider apimart_image2 --image-key <KEY>`
4. Run doctor:
   - Windows PowerShell: `.\scripts\doctor.ps1`
   - macOS/Linux: `bash scripts/doctor.sh`
5. Run the 30 second demo:
   - Windows PowerShell: `.\scripts\run_demo.ps1`
   - macOS/Linux: `bash scripts/run_demo.sh`
6. Report:
   - final video path
   - project directory
   - duration, size, AV delta from `composition_report.json`

## Optional Cover Generation

Use `scripts/generate_cover_302.py` for platform covers. The visual style is fixed to the approved YouTube-style editorial whiteboard cover; only dimensions should change per platform.

Example:

```powershell
python scripts/generate_cover_302.py `
  --platform youtube `
  --title "视频主标题" `
  --subtitle "核心亮点" `
  --topic "视频内容摘要" `
  --subject "central visual subject" `
  --left-context "origin or historical scene" `
  --right-context "modern consequence scene" `
  --timeline "节点1|节点2|节点3|节点4" `
  --output output/covers/example_youtube.png
```

Supported presets: `youtube`, `bilibili`, `wechat`, `xiaohongshu`, `douyin`, `kuaishou`.

## Success Criteria

A successful demo creates:

- `output/demo/latest/final_video.mp4`
- `output/demo/latest/composition_report.json`

The report should show:

- `output_width: 1920`
- `output_height: 1080`
- `single_line_subtitles: true`
- `output_av_delta_seconds` less than `0.1`

## Important Rules

- Never commit or print full API keys.
- Never commit `auto-whiteboard/config/config.ini`.
- Never commit `skills/whiteboard-video-workflow/.env`.
- Do not commit `output/`, generated videos, generated images, or temporary files.
- If API calls fail, first check provider balance, rate limits, and key placement.

## Main Command

After configuration, the core command is:

```powershell
python auto-whiteboard/scripts/auto_generate.py `
  --input examples/demo_30s.txt `
  --output-dir output/demo `
  --project-dir output/demo/latest `
  --bgm skills/whiteboard-animation/assets/bgm/relaxing-piano-for-sleeping-312507.mp3 `
  --bgm-volume -28 `
  --tts-concurrency 16 `
  --whiteboard-jobs 4 `
  --keep-temp
```

The default BGM is configured in `auto-whiteboard/config/config.ini`; the demo scripts also pass it explicitly.
