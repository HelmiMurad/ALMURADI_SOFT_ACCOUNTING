
@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Build M-ERP Desktop

where py >nul 2>nul
if errorlevel 1 (
    echo Please install Python 3.11 or newer.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-desktop.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

python -m PyInstaller --noconfirm --clean --onedir --windowed --name "M-ERP" --icon "static\m-erp.ico" --add-data "templates;templates" --add-data "static;static" --hidden-import webview --collect-all webview desktop_launcher.py

if errorlevel 1 (
    echo Build failed. Check the errors above.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\M-ERP\M-ERP.exe
echo Copy the entire M-ERP folder to another Windows computer.
echo.
pause
