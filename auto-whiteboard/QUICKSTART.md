# Quickstart

From the repository root:

## 1. Bootstrap

Windows:

```powershell
.\scripts\bootstrap.ps1
```

macOS/Linux:

```bash
bash scripts/bootstrap.sh
```

## 2. Configure API Keys

Interactive:

```bash
python scripts/configure_keys.py
```

Non-interactive example:

```bash
python scripts/configure_keys.py \
  --tts-key YOUR_302_OR_MINIMAX_KEY \
  --image-provider apimart_image2 \
  --image-key YOUR_IMAGE_KEY \
  --non-interactive
```

## 3. Check Environment

Windows:

```powershell
.\scripts\doctor.ps1
```

macOS/Linux:

```bash
bash scripts/doctor.sh
```

## 4. Run Demo

Windows:

```powershell
.\scripts\run_demo.ps1
```

macOS/Linux:

```bash
bash scripts/run_demo.sh
```

Expected output:

```text
output/demo/latest/final_video.mp4
```

## 5. Generate Your Own Video

Put a transcript in a text file, then run:

```bash
python auto-whiteboard/scripts/auto_generate.py \
  --input path/to/script.txt \
  --output-dir output/my-video \
  --bgm skills/whiteboard-animation/assets/bgm/relaxing-piano-for-sleeping-312507.mp3 \
  --bgm-volume -28 \
  --tts-concurrency 16 \
  --whiteboard-jobs 4 \
  --keep-temp
```

Default BGM is enabled in `config/config.ini`; the command above passes the recommended BGM explicitly.
