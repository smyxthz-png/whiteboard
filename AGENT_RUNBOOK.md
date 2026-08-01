# Agent Runbook

This runbook is the operational checklist for a fresh clone.

## 1. Inspect

```bash
git status --short
python --version
ffmpeg -version
ffprobe -version
```

Use Python 3.11 or 3.12. Do not modify or delete unrelated user files in a dirty worktree.

## 2. Bootstrap

Run the platform bootstrap script. It creates the root `.venv`, installs the pinned 302.AI CLI and Python dependencies, copies ignored local configuration templates, and prepares `skills/whiteboard-animation/.venv`.

Bootstrap is designed to be idempotent and may be run again after dependency changes.

## 3. Configure Secrets

Interactive:

```bash
python scripts/configure_keys.py
```

Non-interactive:

```bash
python scripts/configure_keys.py \
  --non-interactive \
  --tts-key "$TTS_KEY" \
  --image-provider apimart_image2 \
  --image-key "$IMAGE_KEY" \
  --cover-key "$AI302_KEY"
```

The script writes only ignored local files and masks secrets in its status output.

## 4. Diagnose

```bash
python scripts/doctor.py
python scripts/doctor.py --require-cover
```

The first command validates video generation. The second additionally requires a configured cover key. Doctor does not make billable API calls.

## 5. Run Demo

Use `scripts/run_demo.ps1` or `scripts/run_demo.sh`. The demo writes to the deterministic `output/demo/latest` directory so a failed run can resume.

Do not claim success only because the command exits. Verify the MP4 exists and inspect `composition_report.json`.

## 6. Generate User Content

Use `skills/auto-whiteboard-video/SKILL.md`. Always provide a stable `--project-dir` derived from the requested project name. Use force flags only for stages that must be regenerated.

For covers, use `skills/youtube-cover-generator/SKILL.md`. Keep the approved art direction fixed and change only content and platform dimensions.

## 7. Troubleshoot

| Failure | First checks |
| --- | --- |
| `ffmpeg` missing | Install it and reopen the terminal so PATH refreshes. |
| TTS 401/403 | Key placement, endpoint, account balance. |
| Image failures | Provider selection, key, quota, concurrency, returned aspect ratio. |
| Cover CLI missing | Re-run bootstrap; the executable lives in the root `.venv`. |
| Whiteboard import error | Re-run `skills/whiteboard-animation/scripts/setup_env.py`. |
| Slow rerun | Confirm the same `--project-dir` is used and force flags are absent. |

## 8. Pre-Commit Quality Gate

```bash
python -m unittest discover -s auto-whiteboard/tests -p "test_*.py"
python scripts/validate_repo.py
python scripts/check_no_secrets.py
python scripts/generate_cover_302.py --title "CI test" --dry-run
git diff --check
git status --short
```

Do not stage generated output or local credentials. Report any check that could not be run.
