@echo off
chcp 65001 >nul
rem Double-click on the server laptop: downloads the latest version from GitHub and restarts the portal. Keeps passwords and data.
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'" & exit /b)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update.ps1"
pause
