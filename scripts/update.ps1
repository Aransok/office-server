# Update the server from GitHub (Administrator). Keeps .env, portal.db, .venv and logs. Usage: .\update.ps1
$ErrorActionPreference = 'Stop'
$R = 'C:\OfficeServer'
$tmp = Join-Path $env:TEMP 'osupdate'
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $tmp | Out-Null
Invoke-WebRequest 'https://github.com/Aransok/office-server/archive/refs/heads/main.zip' -OutFile "$tmp\u.zip" -UseBasicParsing
Expand-Archive "$tmp\u.zip" $tmp
$src = Get-ChildItem $tmp -Directory | Select-Object -First 1
Stop-Service OfficePortal
try {
  robocopy $src.FullName $R /E /XF .env portal.db secrets.local.txt /XD .venv logs .git /NFL /NDL /NJH /NJS /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
  & "$R\portal\.venv\Scripts\pip.exe" install -q -r "$R\portal\requirements.txt"
} finally { Start-Service OfficePortal }
Remove-Item $tmp -Recurse -Force
"Updated. Portal restarted."
