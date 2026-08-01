# Contributing

Thanks for helping improve Whiteboard Video Maker.

## Development Setup

Run the platform bootstrap script, configure local keys, and run `scripts/doctor.py`. Never commit local configuration, generated media, transcripts containing private material, or API credentials.

## Checks

Before opening a pull request:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s auto-whiteboard\tests -p "test_*.py"
.\.venv\Scripts\python.exe scripts\doctor.py
.\.venv\Scripts\python.exe scripts\check_no_secrets.py
git diff --check
```

Validate the cover Skill after changing it:

```powershell
.\.venv\Scripts\python.exe C:\Users\<you>\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\youtube-cover-generator
```

## Pull Requests

- Keep changes focused.
- Preserve the locked `1920x1080` video, subtitle, image-ratio, BGM, and cover-style defaults unless the change is explicitly meant to revise them.
- Add or update tests for subtitle normalization and shared workflow behavior.
- Include a sample output or screenshot when changing visual behavior.
