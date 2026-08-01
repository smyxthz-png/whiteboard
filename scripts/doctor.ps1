param(
  [switch]$RequireCover,
  [switch]$Json
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}
Set-Location $Root
$Args = @()
if ($RequireCover) { $Args += "--require-cover" }
if ($Json) { $Args += "--json" }
& $Python (Join-Path $Root "scripts\doctor.py") @Args
