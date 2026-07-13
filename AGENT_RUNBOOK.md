# Whiteboard Video Agent Runbook

This runbook helps Codex, Claude Code, OpenClaw, and similar agents install and validate the project from a fresh clone.

## What This Project Does

Input text becomes a whiteboard explainer video:

1. Split text into short subtitle chunks.
2. Generate MiniMax/302 voiceover and word-timed subtitles.
3. Generate abstract whiteboard images with a `gpt-image-2` provider.
4. Animate images into whiteboard drawing segments.
5. Mix narration with low-volume piano BGM.
6. Burn subtitles and compose the final MP4.
7. Generate platform covers with a locked editorial whiteboard thumbnail style.

Production video size is locked to `1920x1080`. GPT Image 2 source requests use `1792x1008`; downloaded images must be within 3% of 16:9 before they can enter the `1920x1080` whiteboard renderer. The ASS subtitle canvas and final MP4 remain `1920x1080`.

## Required Tools

- Python 3.11 or 3.12
- ffmpeg and ffprobe available in PATH
- Network access to selected TTS/image providers

## Files That Must Exist After Bootstrap

- `auto-whiteboard/config/config.ini`
- `skills/whiteboard-video-workflow/.env`
- `.venv/` at repository root
- `skills/whiteboard-animation/.venv/`

## Provider Configuration

Default TTS:

- `auto-whiteboard/config/config.ini`
- `[TTS].provider = minimax`
- `[MiniMax].api_key = <user key>`

Default image provider:

- `skills/whiteboard-video-workflow/.env`
- `IMAGE_PROVIDER=apimart_image2`
- `APIMART_API_KEY=<user key>`

The configure script supports APIMart, Kie, T8, and macode-compatible providers.

## Demo Command

Use scripts when possible:

```powershell
.\scripts\run_demo.ps1
```

or:

```bash
bash scripts/run_demo.sh
```

Manual fallback:

```bash
python auto-whiteboard/scripts/auto_generate.py \
  --input examples/demo_30s.txt \
  --output-dir output/demo \
  --project-dir output/demo/latest \
  --bgm skills/whiteboard-animation/assets/bgm/relaxing-piano-for-sleeping-312507.mp3 \
  --bgm-volume -28 \
  --tts-concurrency 16 \
  --whiteboard-jobs 4 \
  --keep-temp \
  --force-compose
```

## Expected Outputs

- `output/demo/latest/final_video.mp4`
- `output/demo/latest/voiceover.wav`
- `output/demo/latest/subtitles.srt`
- `output/demo/latest/composition_report.json`
- `output/demo/latest/run_state.json`

`composition_report.json` should report:

- `output_width: 1920`
- `output_height: 1080`
- `single_line_subtitles: true`
- `output_av_delta_seconds < 0.1`

## Troubleshooting

If `config.ini` is missing:

```bash
python scripts/configure_keys.py
```

If `.env` is missing:

```bash
python scripts/configure_keys.py
```

If ffmpeg is missing:

- Windows: install from <https://www.gyan.dev/ffmpeg/builds/> or use Chocolatey.
- macOS: `brew install ffmpeg`
- Linux: `sudo apt-get install ffmpeg`

If whiteboard rendering imports fail, run:

```bash
python skills/whiteboard-animation/scripts/setup_env.py
```

If image generation fails:

- Confirm selected provider in `.env`.
- Confirm image API key.
- Confirm account balance/quota.
- Reduce concurrency in `.env` if the provider rate limits.

If TTS fails:

- Confirm `[MiniMax].api_key`.
- Confirm `[MiniMax].api_url`.
- Confirm provider balance/quota.

## Cover Generation

Use `scripts/generate_cover_302.py` for covers. Do not invent a new cover art direction for each platform; the script locks the preferred YouTube-style visual system and only changes dimensions.

```powershell
.\.venv\Scripts\python.exe scripts\generate_cover_302.py `
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

Platform presets: `youtube`, `bilibili`, `wechat`, `xiaohongshu`, `douyin`, `kuaishou`. Override with `--width` and `--height` only when a platform has a specific delivery requirement.

## Security Checklist Before Pushing

Run:

```bash
python scripts/check_no_secrets.py
git status --short
```

Make sure these files are not staged:

- `auto-whiteboard/config/config.ini`
- `skills/whiteboard-video-workflow/.env`
- anything under `output/`
