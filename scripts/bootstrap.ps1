param(
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"

Set-Location $Root

if (-not $Python) {
  $Candidates = @("py -3.12", "py -3.11", "python")
  foreach ($Candidate in $Candidates) {
    $Parts = $Candidate.Split(" ")
    $Exe = $Parts[0]
    $Args = @()
    if ($Parts.Count -gt 1) { $Args = $Parts[1..($Parts.Count - 1)] }
    try {
      & $Exe @Args --version *> $null
      if ($LASTEXITCODE -eq 0) {
        $Python = $Candidate
        break
      }
    } catch {}
  }
}
if (-not $Python) {
  throw "Could not find Python. Install Python 3.12 or 3.11."
}

$PythonParts = $Python.Split(" ")
$PythonExe = $PythonParts[0]
$PythonBaseArgs = @()
if ($PythonParts.Count -gt 1) { $PythonBaseArgs = $PythonParts[1..($PythonParts.Count - 1)] }

Write-Host "[1/6] Checking Python..."
& $PythonExe @PythonBaseArgs --version

if (-not (Test-Path $VenvPython)) {
  Write-Host "[2/6] Creating root virtual environment..."
  & $PythonExe @PythonBaseArgs -m venv $Venv
} else {
  Write-Host "[2/6] Root virtual environment exists."
}

Write-Host "[3/6] Installing Python dependencies..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $Root "auto-whiteboard\requirements.txt")

Write-Host "[4/6] Preparing local config files..."
$Config = Join-Path $Root "auto-whiteboard\config\config.ini"
$ConfigExample = Join-Path $Root "auto-whiteboard\config\config.example.ini"
$Env = Join-Path $Root "skills\whiteboard-video-workflow\.env"
$EnvExample = Join-Path $Root "skills\whiteboard-video-workflow\.env.example"
if (-not (Test-Path $Config)) { Copy-Item $ConfigExample $Config }
if (-not (Test-Path $Env)) { Copy-Item $EnvExample $Env }

Write-Host "[5/6] Preparing whiteboard animation environment..."
& $VenvPython (Join-Path $Root "skills\whiteboard-animation\scripts\setup_env.py")

Write-Host "[6/6] Checking ffmpeg..."
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
  Write-Warning "ffmpeg/ffprobe is missing. Install ffmpeg, then run .\scripts\doctor.ps1."
} else {
  Write-Host "[OK] ffmpeg and ffprobe found."
}

Write-Host ""
Write-Host "[OK] Bootstrap complete."
Write-Host "Next:"
Write-Host "  .\.venv\Scripts\python.exe scripts\configure_keys.py"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\doctor.ps1"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1"
