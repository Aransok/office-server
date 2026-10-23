@echo off
chcp 65001 >nul
rem Double-click on the server PC once: lets portal tiles run programs here and show only their window on other PCs.
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'" & exit /b)

echo Turning on Remote Desktop (with network login, local network only)...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f >nul
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 1 /f >nul
rem Group ID and SID instead of names, because the names are translated on Bulgarian Windows
powershell -NoProfile -Command "Get-NetFirewallRule -Group '@FirewallAPI.dll,-28752' | Set-NetFirewallRule -Enabled True -RemoteAddress LocalSubnet"

echo Allowing single-program windows (RemoteApp)...
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList" /v fDisabledAllowList /t REG_DWORD /d 1 /f >nul

echo Creating the officeapp account...
net user officeapp >nul 2>&1 && (echo officeapp already exists, password unchanged.) || powershell -NoProfile -Command "$p = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 16 | ForEach-Object {[char]$_}); New-LocalUser officeapp -Password (ConvertTo-SecureString $p -AsPlainText -Force) -PasswordNeverExpires -UserMayNotChangePassword | Out-Null; Add-LocalGroupMember -SID S-1-5-32-555 -Member officeapp; Add-Content '%~dp0secrets.local.txt' ('officeapp password: ' + $p); Write-Host ('officeapp password (also in secrets.local.txt): ' + $p)"

echo.
echo Done. Next: sign in once as officeapp, open each program and log in so it remembers.
echo Then in the portal click the "run on server" button next to the program. Only one remote user at a time on Windows 10 Pro.
pause
