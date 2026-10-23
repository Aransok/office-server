@echo off
chcp 65001 >nul
rem One-click PC setup: drive O:, certificate, shortcuts. Needs no Python or anything else.
rem root.crt must be in the same folder (downloaded from the portal with this file).
set SERVER=OFFICE-SERVER
echo.
echo === 1/4 Drive O: ===
set /p U=Username (e.g. joro):
net use O: /delete /y >nul 2>&1
net use O: \\%SERVER%\Office * /user:%SERVER%\%U% /persistent:yes
if errorlevel 1 (echo ERROR: cannot connect. Check the network, username and password. & pause & exit /b 1)
echo.
echo === 2/4 Portal certificate (it will ask for administrator, answer Yes) ===
if not exist "%~dp0root.crt" (echo ERROR: root.crt is missing next to this file. Download it from the portal. & pause & exit /b 1)
powershell -NoProfile -Command "Start-Process certutil -ArgumentList '-addstore','-f','Root','%~dp0root.crt' -Verb RunAs -Wait"
curl.exe -s -o nul https://%SERVER%/login && (echo Certificate is trusted.) || (echo WARNING: certificate not accepted. The browser will warn on the portal.)
echo.
echo === 3/4 Desktop shortcuts ===
for /f "delims=" %%D in ('powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"') do set DESK=%%D
powershell -NoProfile -Command "$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut($env:DESK+'\Office Files.lnk'); $l.TargetPath='O:\'; $l.Save()"
(echo [InternetShortcut]& echo URL=https://%SERVER%)> "%DESK%\Office Portal.url"
echo.
echo === 4/4 App launcher (opens programs from the portal) ===
if exist "O:\_launcher\officeapp.ps1" (
  mkdir "%LOCALAPPDATA%\OfficeApp" 2>nul
  copy /y "O:\_launcher\officeapp.ps1" "%LOCALAPPDATA%\OfficeApp\" >nul
  copy /y "O:\_launcher\OfficeLauncher.ps1" "%LOCALAPPDATA%\OfficeApp\" >nul
  powershell -NoProfile -Command "$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut($env:DESK+'\Office.lnk'); $l.TargetPath='powershell.exe'; $q=[char]34; $l.Arguments='-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File '+$q+$env:LOCALAPPDATA+'\OfficeApp\OfficeLauncher.ps1'+$q; $l.IconLocation='imageres.dll,109'; $l.Save()"
  reg add HKCU\Software\Classes\officeapp /ve /d "URL:Office App" /f >nul
  reg add HKCU\Software\Classes\officeapp /v "URL Protocol" /d "" /f >nul
  reg add HKCU\Software\Classes\officeapp\shell\open\command /ve /d "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%LOCALAPPDATA%\OfficeApp\officeapp.ps1\" \"%%1\"" /f >nul
) else (echo WARNING: launcher not found on the server yet. Restart the portal service and run this again.)
echo.
echo Done. The desktop now has "Office" (the program launcher), "Office Files" (the folders) and "Office Portal" (browser).
echo Firefox has its own certificate store: accept the certificate separately in the browser.
pause
