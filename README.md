# Whiteboard Video Maker

Generate narrated Chinese whiteboard videos from plain text.

The workflow can:

1. Split a transcript into subtitle chunks.
2. Generate MiniMax/302 voiceover and subtitles.
3. Generate abstract whiteboard images with a `gpt-image-2` image provider.
4. Render hand-drawn whiteboard animation segments.
5. Mix low-volume piano background music.
6. Compose the final MP4 with burned-in subtitles.
7. Generate platform covers with one locked editorial whiteboard thumbnail style.

Production video size is locked to `1920x1080`. GPT Image 2 source requests use the native `1792x1008` 16:9 size, accept up to 3% aspect-ratio drift from providers, and are normalized to the `1920x1080` animation canvas. Clear 3:2, square, or portrait responses are rejected and regenerated.

## For Friends Using An Agent

Give your agent this prompt:

```text
Please install and run this whiteboard video project: <GitHub URL>.
Follow AGENTS.md and AGENT_RUNBOOK.md.
Ask me only for the required API keys.
Run the 30 second demo first and report the final video path.
```

The agent should run:

```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\python.exe scripts\configure_keys.py
.\scripts\doctor.ps1
.\scripts\run_demo.ps1
```

On macOS/Linux:

```bash
bash scripts/bootstrap.sh
./.venv/bin/python scripts/configure_keys.py
bash scripts/doctor.sh
bash scripts/run_demo.sh
```

## Required Keys

Minimum setup:

- MiniMax or 302.ai API key for TTS
- One image provider API key

Supported image providers:

- APIMart: `apimart_image2`
- Kie AI: `kie_image2`
- T8: `t8_image2`
- macode/OpenAI-compatible: `macode_image2`

Claude is optional. The default demo uses rule-based splitting, so a Claude key is not required.

## Manual Demo Command

After bootstrap and configuration:

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

Expected output:

```text
output/demo/latest/final_video.mp4
output/demo/latest/composition_report.json
```

`composition_report.json` should include `output_width: 1920` and `output_height: 1080`.

## Cover Generation

The cover style is fixed to the preferred YouTube thumbnail direction: premium editorial whiteboard, flat warm off-white background, dark marker linework, restrained amber accent, readable but sparse Chinese text, and abstract faceless round-headed characters.

Only the canvas size changes by platform:

```powershell
.\.venv\Scripts\python.exe scripts\generate_cover_302.py `
  --platform youtube `
  --title "啤酒如何建造文明" `
  --subtitle "1万年历史" `
  --topic "啤酒如何推动农业、城市和现代社交" `
  --subject "large amber beer glass" `
  --left-context "ancient Sumerian temple and grain jars" `
  --right-context "modern city, factory, and people raising glasses" `
  --timeline "1万年前|苏美尔|中世纪|工业革命|今天" `
  --output output/covers/beer_youtube.png
```

Supported presets: `youtube`, `bilibili`, `wechat`, `xiaohongshu`, `douyin`, `kuaishou`.

## Local Files Not To Commit

These are intentionally ignored:

- `auto-whiteboard/config/config.ini`
- `skills/whiteboard-video-workflow/.env`
- `output/`
- generated videos, generated images, temporary files

Before pushing:

```bash
python scripts/check_no_secrets.py
git status --short
```

## Useful Docs

- `AGENTS.md`: short install instructions for coding agents
- `AGENT_RUNBOOK.md`: detailed troubleshooting runbook
- `CLAUDE.md`: Claude Code entrypoint
