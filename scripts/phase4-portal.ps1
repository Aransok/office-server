# Phase 4 (Administrator): venv, .env, tests, admin user, Caddy + WinSW services, firewall.
# Needs Python 3.11+ ("py") and internet for Caddy and WinSW.
param([string]$DataRoot = $(if (Test-Path D:\) { 'D:\OfficeData' } else { 'C:\OfficeData' }), [string]$Site = 'OFFICE-SERVER')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # PS 5.1 downloads crawl with the progress bar on
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$R = 'C:\OfficeServer'; $P = "$R\portal"
New-Item -ItemType Directory -Force "$R\logs","$R\caddy\data","$R\services","$R\client" | Out-Null
if (-not (Test-Path "$P\.venv")) { py -3 -m venv "$P\.venv" }
& "$P\.venv\Scripts\pip" install -q -r "$P\requirements.txt"
if (-not (Test-Path "$P\.env")) {
  "DATA_ROOT=$DataRoot`nCOOKIE_SECURE=1`nNTFS_RIGHTS=1`nMAX_UPLOAD_MB=500`nLOG_DIR=$R\logs`nSTATUS_FILE=$R\logs\backup-status.json`nCLIENT_DIR=$R\client" | Set-Content "$P\.env" -Encoding UTF8
}
& "$P\.venv\Scripts\python" -m pytest -q "$P\tests"
if ($LASTEXITCODE) { throw 'tests failed, not installing' }
Push-Location $P
& ".venv\Scripts\python" -m app.cli create-admin admin   # prints the password ONCE; says "already exists" on rerun
Pop-Location
if (-not (Test-Path "$R\caddy\caddy.exe")) {   # GitHub, not caddyserver.com/api/download: that endpoint stalled
  Invoke-WebRequest 'https://github.com/caddyserver/caddy/releases/download/v2.10.0/caddy_2.10.0_windows_amd64.zip' -OutFile "$R\caddy\caddy.zip"
  Expand-Archive "$R\caddy\caddy.zip" "$R\caddy" -Force; Remove-Item "$R\caddy\caddy.zip"
}
if (-not (Test-Path "$R\services\WinSW.exe")) { Invoke-WebRequest 'https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe' -OutFile "$R\services\WinSW.exe" }
"https://${Site} {`n  tls internal`n  reverse_proxy 127.0.0.1:8080`n}" | Set-Content "$R\caddy\Caddyfile" -Encoding ASCII
function Svc($name, $exe, $arguments, $dir, $envs) {
  Copy-Item "$R\services\WinSW.exe" "$R\services\$name.exe" -Force
  @"
<service><id>$name</id><name>$name</name><description>$name</description>
<executable>$exe</executable><arguments>$arguments</arguments><workingdirectory>$dir</workingdirectory>
$envs<onfailure action="restart" delay="10 sec"/><startmode>Automatic</startmode>
<logpath>$R\logs</logpath><log mode="roll"/></service>
"@ | Set-Content "$R\services\$name.xml" -Encoding UTF8
  if (-not (Get-Service $name -ErrorAction SilentlyContinue)) { & "$R\services\$name.exe" install }
  & "$R\services\$name.exe" restart
}
Svc 'OfficePortal' "$P\.venv\Scripts\python.exe" '-m uvicorn app.main:app --host 127.0.0.1 --port 8080' $P ''
Svc 'OfficeCaddy' "$R\caddy\caddy.exe" 'run --config Caddyfile' "$R\caddy" '<env name="XDG_DATA_HOME" value="C:\OfficeServer\caddy\data"/>'
if (-not (Get-NetFirewallRule 'Office HTTPS 443' -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName 'Office HTTPS 443' -Direction Inbound -Protocol TCP -LocalPort 443 -Profile Private -RemoteAddress LocalSubnet -Action Allow | Out-Null
}
Start-Sleep 5
$crt = "$R\caddy\data\caddy\pki\authorities\local\root.crt"
if (Test-Path $crt) { Copy-Item $crt "$R\client\root.crt" -Force; "root.crt copied to client\" } else { "root.crt not there yet; rerun in a minute" }
"[InternetShortcut]`nURL=https://$Site" | Set-Content "$R\client\Офис портал.url" -Encoding ASCII
Copy-Item "$R\client\Офис портал.url" ([Environment]::GetFolderPath('CommonDesktopDirectory')) -Force
"--- verify ---"
Get-Service OfficePortal,OfficeCaddy | Select-Object Name,Status
