@echo off
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    py -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller. Make sure Python is installed.
        pause
        exit /b 1
    )
)

py -m PyInstaller --onefile --windowed --name "dlp-ui" dlp-ui.py

echo.
if exist "dist\dlp-ui.exe" (
    echo Build successful: dist\dlp-ui.exe
) else (
    echo Build may have failed. Check the output above.
)
pause
