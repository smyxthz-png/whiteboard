param(
  [string]$InputFile = "examples\demo_30s.txt",
  [string]$ProjectDir = "output\demo\latest",
  [int]$TtsConcurrency = 16,
  [int]$WhiteboardJobs = 4
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

Set-Location $Root

& $Python "auto-whiteboard\scripts\auto_generate.py" `
  --input $InputFile `
  --output-dir "output\demo" `
  --project-dir $ProjectDir `
  --bgm "skills\whiteboard-animation\assets\bgm\relaxing-piano-for-sleeping-312507.mp3" `
  --bgm-volume -28 `
  --tts-concurrency $TtsConcurrency `
  --whiteboard-jobs $WhiteboardJobs `
  --keep-temp `
  --force-compose
