@echo off
setlocal

cd /d "%~dp0"
title RC N1 Bridge - Install Dependencies

echo RC N1 Bridge dependency installer
echo ==================================
echo.
echo This will:
echo   1. Install Python 3.12 if needed, then create the local environment.
echo   2. Install the locked Python and virtual-gamepad dependencies.
echo   3. Download and launch DJI Assistant 2 for the USB VCOM driver.
echo.
echo Windows may ask you to approve driver installation. You must accept
echo those installer prompts manually.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-dependencies.ps1" %*
if errorlevel 1 (
    echo.
    echo Dependency installation did not complete successfully.
    echo Review the error above, then run this file again.
    pause
    exit /b 1
)

echo.
echo Dependencies are ready. You can now double-click run.bat.
pause
endlocal
