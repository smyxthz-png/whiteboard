---
name: youtube-cover-generator
description: Generate YouTube thumbnails and other platform video covers in this repository's locked editorial whiteboard style. Use when the user asks for a YouTube thumbnail, video cover, Chinese social cover, Bilibili cover, or wants the established cover style reused at another platform size.
---

# YouTube Cover Generator

Generate covers through the repository wrapper instead of writing a new prompt or calling an image API directly.

## Workflow

1. Confirm the repository was bootstrapped and `AI302_KEY` is configured.
2. Extract a concise title, one optional numeric/hook badge, a central subject, an origin scene, a modern consequence scene, and up to six timeline labels from the transcript.
3. Run `scripts/generate_cover.py` from this skill directory. Default to `youtube` when the user does not name a platform.
4. Check that the image and `.prompt.txt` file exist. Report both absolute paths.

```powershell
python skills/youtube-cover-generator/scripts/generate_cover.py `
  --platform youtube `
  --title "Main Chinese title" `
  --subtitle "Core hook or number" `
  --topic "Short content summary" `
  --subject "central visual subject" `
  --left-context "historical origin scene" `
  --right-context "modern consequence scene" `
  --timeline "Milestone 1|Milestone 2|Milestone 3|Today" `
  --output output/covers/example_youtube.png
```

Use `--dry-run --print-prompt` to validate the prompt without spending API credits.

## Locked Style

- Keep a flat warm off-white `#F6F1E3` background.
- Use dark charcoal marker lines and restrained amber accents.
- Use abstract faceless circular-headed people with no hair or facial features.
- Let the illustration dominate; use only one title, one optional badge, and short timeline labels.
- Do not add paragraphs, dense Chinese text, photorealism, 3D, gradients, texture, white patches, or cutout boxes.
- Change only composition and canvas dimensions between platforms; do not invent a new art direction.

## Platform Presets

- `youtube`, `bilibili`, `wechat`: `1280x720`
- `xiaohongshu`: `1440x1920`
- `douyin`, `kuaishou`: `1080x1920`

Use explicit `--width` and `--height` only when the delivery platform requires a different size.
