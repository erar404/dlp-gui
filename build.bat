@echo off
setlocal enabledelayedexpansion
echo === MD Tools Build Script ===
echo.

REM ── Python ────────────────────────────────────────────────────────────────────
where py >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python and try again.
    pause & exit /b 1
)

REM ── PyInstaller ───────────────────────────────────────────────────────────────
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    py -m pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller.
        pause & exit /b 1
    )
)

REM ── Bundled deps ──────────────────────────────────────────────────────────────
py download_deps.py
if errorlevel 1 (
    echo.
    echo ERROR: Dependency download failed. Check the output above.
    pause & exit /b 1
)

REM ── Build ─────────────────────────────────────────────────────────────────────
echo Building MD-Tools.exe...
py -m PyInstaller dlp-ui.spec

echo.
if exist "dist\MD-Tools.exe" (
    echo Build successful: dist\MD-Tools.exe
) else (
    echo Build may have failed. Check the output above.
)
pause
