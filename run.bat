@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo RC N1 Bridge is not set up yet.
    echo.
    echo Double-click install dependencies.bat first.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import tkinter as tk; root=tk.Tk(); root.withdraw(); root.destroy()" >nul 2>&1
if errorlevel 1 (
    echo RC N1 Bridge needs its local Python environment repaired.
    echo.
    echo Double-click install dependencies.bat to repair it.
    echo.
    pause
    exit /b 1
)

set "PYTHONPATH=%CD%\src"
".venv\Scripts\python.exe" -m rcn1_bridge gui

if errorlevel 1 (
    echo.
    echo RC N1 Bridge exited with an error.
    pause
)

endlocal
