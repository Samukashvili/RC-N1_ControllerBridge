$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "The virtual environment is missing. Run .\scripts\setup.ps1 first."
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
& $Python -m rcn1_bridge gui

