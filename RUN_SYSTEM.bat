@echo off
chcp 65001 >nul
cd /d "%~dp0"
title ALMURADI SOFT ERP
where py >nul 2>nul
if errorlevel 1 (echo Python is not installed. Install Python 3.11 or newer from https://www.python.org/downloads/ & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" (py -3 -m venv .venv)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (echo Package installation failed. Check internet and try again.& pause & exit /b 1)
set APP_SECRET_KEY=local-dev-secret-change-this-before-public-deployment
start "" http://127.0.0.1:8000
python app.py
pause
