@echo off
chcp 65001 >nul
cd /d "%~dp0"
title ALMURADI SOFT ERP - Mode Selector
where py >nul 2>nul
if errorlevel 1 (echo ثبّت Python 3.11 أو أحدث أولاً.& pause& exit /b 1)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
call .venv\Scripts\activate.bat
python LAUNCHER.py
