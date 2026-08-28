$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VirtualEnv = Join-Path $ProjectRoot ".venv"

if (-not (Test-Path -LiteralPath $VirtualEnv)) {
    python -m venv $VirtualEnv
}

$Python = Join-Path $VirtualEnv "Scripts\python.exe"
& $Python -m pip install --require-hashes -r (Join-Path $ProjectRoot "requirements.lock")

Write-Host ""
Write-Host "Setup complete. If the ViGEmBus installer appeared, finish it before starting."
Write-Host "Run: .\scripts\run.ps1"
