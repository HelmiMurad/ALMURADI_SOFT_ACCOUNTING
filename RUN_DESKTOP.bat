@echo off
chcp 65001 >nul
cd /d "%~dp0"
title M-ERP | المرادي سوفت
where py >nul 2>nul
if errorlevel 1 (echo ثبّت Python 3.11 أو أحدث من python.org ثم أعد المحاولة.& pause& exit /b 1)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-desktop.txt
if errorlevel 1 (echo تعذر تثبيت المتطلبات. تحقق من اتصال الإنترنت.& pause& exit /b 1)
python desktop_launcher.py
if errorlevel 1 pause
