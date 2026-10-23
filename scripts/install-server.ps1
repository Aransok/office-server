# One-shot server install (Administrator): power, Python, share, portal, HTTPS, services, backup if a USB drive is plugged in.
# Safe to run again: it skips what is already done. Started by INSTALL-SERVER.cmd.
$ErrorActionPreference = 'Stop'
$R = 'C:\OfficeServer'
try {
  if ((Split-Path $PSScriptRoot -Parent) -ne $R) {   # the scripts assume C:\OfficeServer
    robocopy (Split-Path $PSScriptRoot -Parent) $R /E /XD .venv .git /NFL /NDL /NJH /NJS /NP | Out-Null
    & "$R\scripts\install-server.ps1"; return
  }
  $S = "$R\scripts"
  $name = Read-Host "Server name on the network (press Enter for OFFICE-SERVER)"
  if (-not $name) { $name = 'OFFICE-SERVER' }
  "== 1/5 Computer settings (power, network, updates)"
  if ($env:COMPUTERNAME -ne $name) {
    & "$S\phase1-server.ps1" -NewName $name
    Write-Host "`nThe computer was renamed to $name. RESTART it, then run INSTALL-SERVER.cmd again." -ForegroundColor Yellow
    return
  }
  & "$S\phase1-server.ps1"
  "== 2/5 Python"
  & "$S\install-python.ps1"
  $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
  "== 3/5 Folders and sharing"
  & "$S\phase2-share.ps1"
  "== 4/5 Portal, HTTPS, services"
  $out = & "$S\phase4-portal.ps1" -Site $name | Tee-Object -Variable log
  $admin = ($log | Select-String 'password:\s*(\S+)').Matches | ForEach-Object { $_.Groups[1].Value } | Select-Object -First 1
  if ($admin) { "admin / $admin  ($(Get-Date -Format s))" | Add-Content "$R\secrets.local.txt" }
  "== 5/5 Backup (nightly copy at 23:00)"
  $usb = Get-Disk | Where-Object BusType -eq 'USB' | Get-Partition | Get-Volume | Where-Object DriveLetter | Select-Object -First 1
  if ($usb -and (Read-Host "External drive found: $($usb.DriveLetter): - use it for backups? (y/n)") -eq 'y') {
    & "$S\phase5-backup.ps1" -BackupDrive "$($usb.DriveLetter):"
  } else {
    "No external drive. Plug it in and run: .\scripts\phase5-backup.ps1 -BackupDrive E:   (use the drive letter)"
  }
  Write-Host "`n=== DONE ===" -ForegroundColor Green
  "Portal: https://$name"
  if ($admin) { "User: admin   Password: $admin   (also saved in $R\secrets.local.txt)" }
  else { "Admin already exists. New password: cd $R\portal; .\.venv\Scripts\python -m app.cli reset-password admin" }
  "Next: log in to the portal, open the Users page and create the people. They use client\setup.cmd, downloadable from the Programs page."
} catch {
  Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Send this text to your helper. You can run the script again."
}
