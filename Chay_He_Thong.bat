@echo off
cd /d "%~dp0"
title SafeVoice AI - Windows
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-Windows.ps1" %*
if errorlevel 1 (
    echo Khoi dong that bai. Xem loi ben tren.
    pause
    exit /b 1
)
