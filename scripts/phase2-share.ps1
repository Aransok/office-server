# Phase 2 (Administrator): folders, OfficeUsers group, users, NTFS, SMB share, firewall.
# Example: .\phase2-share.ps1 -Users ivan,maria -Folders 'Общи','Счетоводство'
param([string]$DataRoot, [string[]]$Users = @(), [string[]]$Folders = @('Общи','Счетоводство','Склад','ТРЗ','Документи','Сканирани'))
$ErrorActionPreference = 'Stop'
if (-not $DataRoot) { $DataRoot = if (Test-Path D:\) { 'D:\OfficeData' } else { 'C:\OfficeData' } }
$sec = 'C:\OfficeServer\secrets.local.txt'
New-Item -ItemType Directory -Force $DataRoot | Out-Null
foreach ($f in $Folders + '_Програми') { New-Item -ItemType Directory -Force (Join-Path $DataRoot $f) | Out-Null }
(New-Item -ItemType Directory -Force (Join-Path $DataRoot '_Корзина')).Attributes = 'Hidden'
if (-not (Get-LocalGroup OfficeUsers -ErrorAction SilentlyContinue)) { New-LocalGroup OfficeUsers -Description 'Office share users' | Out-Null }
Add-Type -AssemblyName System.Web
foreach ($u in $Users) {
  if (Get-LocalUser $u -ErrorAction SilentlyContinue) { "user $u exists, skipped"; continue }
  $pw = [System.Web.Security.Membership]::GeneratePassword(14,3)
  New-LocalUser $u -Password (ConvertTo-SecureString $pw -AsPlainText -Force) -PasswordNeverExpires | Out-Null
  Add-LocalGroupMember OfficeUsers $u
  "$u : $pw" | Add-Content $sec -Encoding UTF8
  "Created $u, password: $pw (also in $sec, shown once)"
}
icacls $DataRoot /grant 'OfficeUsers:(OI)(CI)M' 'Administrators:(OI)(CI)F' /T /C | Out-Null
# start open for everyone; the portal narrows each top folder (NTFS_RIGHTS=1 in its .env, or: python -m app.cli sync-rights)
if (-not (Get-SmbShare Office -ErrorAction SilentlyContinue)) { New-SmbShare Office -Path $DataRoot -ChangeAccess OfficeUsers -FullAccess Administrators | Out-Null }
Set-SmbShare -Name Office -FolderEnumerationMode AccessBased -Force   # people do not even see folders they cannot open
Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force
Get-NetFirewallRule -DisplayGroup 'File and Printer Sharing' | Where-Object { $_.DisplayName -match 'SMB-In' } |
  Set-NetFirewallRule -Enabled True -Profile Private -RemoteAddress LocalSubnet
"--- verify ---"
Get-SmbShare Office
Test-NetConnection localhost -Port 445 | Select-Object TcpTestSucceeded
