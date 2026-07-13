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

Write-Host "[1/5] Checking Python..."
& $PythonExe @PythonBaseArgs --version

if (-not (Test-Path $VenvPython)) {
  Write-Host "[2/5] Creating root virtual environment..."
  & $PythonExe @PythonBaseArgs -m venv $Venv
} else {
  Write-Host "[2/5] Root virtual environment exists."
}

Write-Host "[3/5] Installing Python dependencies..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $Root "auto-whiteboard\requirements.txt")

Write-Host "[4/5] Preparing local config files..."
$Config = Join-Path $Root "auto-whiteboard\config\config.ini"
$ConfigExample = Join-Path $Root "auto-whiteboard\config\config.example.ini"
$Env = Join-Path $Root "skills\whiteboard-video-workflow\.env"
$EnvExample = Join-Path $Root "skills\whiteboard-video-workflow\.env.example"
if (-not (Test-Path $Config)) { Copy-Item $ConfigExample $Config }
if (-not (Test-Path $Env)) { Copy-Item $EnvExample $Env }

Write-Host "[5/5] Preparing whiteboard animation environment..."
& $VenvPython (Join-Path $Root "skills\whiteboard-animation\scripts\setup_env.py")

Write-Host ""
Write-Host "[OK] Bootstrap complete."
Write-Host "Next:"
Write-Host "  .\.venv\Scripts\python.exe scripts\configure_keys.py"
Write-Host "  .\scripts\doctor.ps1"
Write-Host "  .\scripts\run_demo.ps1"
