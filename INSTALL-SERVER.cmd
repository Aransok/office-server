@echo off
chcp 65001 >nul
rem Double-click on the server laptop: installs everything. Asks for admin rights and only the server name.
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'" & exit /b)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-server.ps1"
pause
