@echo off
chcp 65001 >nul
rem Double-click on the server PC once: lets programs run here and show only their window on other PCs (RemoteApp).
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'" & exit /b)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-remote.ps1"
pause
