---
name: whiteboard-animation
description: Convert one or more source images into 1920x1080 whiteboard drawing-animation MP4 segments with an optional hand overlay. Use when the user asks to animate existing images as whiteboard drawings or when debugging the animation stage of the full video pipeline.
---

# Whiteboard Animation

## Prepare

```bash
python skills/whiteboard-animation/scripts/setup_env.py --check
```

If the check fails, run the same command without `--check`. Capture the printed `PYTHON_PATH` and use that interpreter for rendering.

## Single Image

```bash
<PYTHON_PATH> skills/whiteboard-animation/scripts/generate_whiteboard.py input.png \
  --output-dir output/whiteboard \
  --duration 10000 \
  --canvas-width 1920 \
  --canvas-height 1080
```

Add `--no-hand` only when the user explicitly requests animation without the drawing-hand overlay.

## Batch

```bash
<PYTHON_PATH> skills/whiteboard-animation/scripts/batch_generate.py \
  --images scene-1.png scene-2.png \
  --durations 10000 12000 \
  --output-dir output/whiteboard \
  --fps 30 \
  --jobs 4 \
  --canvas-width 1920 \
  --canvas-height 1080
```

Image and duration counts must match. The batch renderer fingerprints inputs and reuses valid segments unless `--force` is supplied.

## Visual Rules

- Preserve the `1920x1080` canvas.
- Use `drawing-hand-v2.png`, which includes a longer forearm to avoid a floating-hand effect near the top edge.
- Keep source images on the uniform `#F6F1E3` background to avoid white patches during reveal animation.
- Verify that every requested segment exists and is a valid H.264 MP4 before returning success.
