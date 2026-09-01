@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0dlp-ui.ps1"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Script failed with code %ERRORLEVEL%
    pause
)
