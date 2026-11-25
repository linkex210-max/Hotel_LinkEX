@echo off
title Hotel LinkEX - Django Server
cd /d "%~dp0.."
echo ===================================================
echo     Hotel LinkEX - Starting Django Backend Server
echo ===================================================
echo.
"%~dp0..\.venv\Scripts\python.exe" "%~dp0..\backend\manage.py" runserver 127.0.0.1:8000
pause
