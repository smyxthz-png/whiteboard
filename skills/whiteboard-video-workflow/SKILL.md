---
name: whiteboard-video-workflow
description: Low-level storyboard and source-image workflow for this repository. Use when debugging or running the SRT-to-storyboard, prompt generation, provider-specific image generation, aspect-ratio validation, or segment merge stages independently of the main auto-whiteboard-video pipeline.
---

# Whiteboard Video Workflow

Prefer `skills/auto-whiteboard-video` for normal end-to-end requests. Use this Skill only for stage-level diagnostics or custom SRT workflows.

## Environment

Provider configuration lives in the ignored `.env` beside this file. Create it through `scripts/configure_keys.py`; do not edit or print secrets during routine runs.

Supported image providers are `apimart_image2`, `kie_image2`, `t8_image2`, and `macode_image2`.

## Components

- `scripts/generate-storyboard.py`: create `storyboard.json` from subtitles and scene groups.
- `scripts/workflow_helper.py`: create output directories, build prompts, and merge segments.
- `scripts/generate-image.py`: generate source images with the configured provider.
- `scripts/banana_prompt_template.py`: enforce the locked whiteboard drawing style.
- `references/storyboard-parser.md`: storyboard rules.
- `references/image-generator.md`: image-provider workflow.

## Invariants

- Keep scene, image, duration, and video arrays in identical order.
- Treat durations as integer milliseconds across the whole pipeline.
- Request near-16:9 source images and reject clear 3:2, square, and portrait responses.
- Normalize accepted images to the flat `#F6F1E3` background before animation.
- Use abstract faceless circular-headed people; text must remain sparse and secondary to drawings.
- Preserve cached outputs unless a fingerprint changes or a force flag is explicitly requested.

## Stage-Level Validation

Run the repository doctor before troubleshooting. After a custom stage run, verify the expected file count and inspect any JSON manifest before continuing to the next stage.
