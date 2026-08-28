$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VirtualEnv = Join-Path $ProjectRoot ".venv"
$VirtualPython = Join-Path $VirtualEnv "Scripts\python.exe"

function Test-BridgePython([string]$Executable) {
    if (-not (Test-Path -LiteralPath $Executable)) {
        return $false
    }
    $PreviousPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & $Executable -c "import sys, tkinter as tk; root=tk.Tk(); root.withdraw(); root.destroy(); raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" *> $null
    $CheckExitCode = $LASTEXITCODE
    $ErrorActionPreference = $PreviousPreference
    return $CheckExitCode -eq 0
}

if (-not (Test-BridgePython $VirtualPython)) {
    if (Test-Path -LiteralPath $VirtualEnv) {
        $ResolvedEnv = (Resolve-Path -LiteralPath $VirtualEnv).Path
        $ExpectedEnv = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot ".venv"))
        if ($ResolvedEnv -ne $ExpectedEnv) {
            throw "Refusing to recreate unexpected virtual environment path: $ResolvedEnv"
        }
        Write-Host "The existing environment cannot load Tkinter; recreating .venv..."
        Remove-Item -LiteralPath $ResolvedEnv -Recurse -Force
    }

    $Candidates = @()
    $LocalPythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path -LiteralPath $LocalPythonRoot) {
        $Candidates += Get-ChildItem -LiteralPath $LocalPythonRoot -Directory |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "python.exe" }
    }
    $PathPython = Get-Command python -ErrorAction SilentlyContinue
    if ($PathPython) {
        $Candidates += $PathPython.Source
    }
    $BasePython = $Candidates | Where-Object { Test-BridgePython $_ } | Select-Object -First 1
    if (-not $BasePython) {
        throw "Python 3.10+ with Tkinter was not found. Install Python from python.org with Tcl/Tk enabled."
    }
    Write-Host "Creating the environment with $BasePython"
    & $BasePython -m venv $VirtualEnv
    if ($LASTEXITCODE -ne 0) {
        throw "Python could not create the virtual environment."
    }
}

& $VirtualPython -m pip install --require-hashes -r (Join-Path $ProjectRoot "requirements.lock")
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

Write-Host ""
Write-Host "Setup complete. If the ViGEmBus installer appeared, finish it before starting."
Write-Host "Run: .\scripts\run.ps1"
