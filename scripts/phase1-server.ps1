# Phase 1 (run as Administrator): power, update hours, Private profile, optional rename.
param([string]$NewName)
$ErrorActionPreference = 'Stop'
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change monitor-timeout-ac 10
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0   # lid close = do nothing
powercfg /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
$wu = 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings'
Set-ItemProperty $wu ActiveHoursStart 7 -Type DWord
Set-ItemProperty $wu ActiveHoursEnd 20 -Type DWord
Get-NetConnectionProfile | Where-Object NetworkCategory -ne Private | Set-NetConnectionProfile -NetworkCategory Private
Get-NetAdapter | Where-Object Status -eq Up | ForEach-Object { "MAC for router DHCP reservation: $($_.Name) $($_.MacAddress)" }
if ($NewName -and $env:COMPUTERNAME -ne $NewName) { Rename-Computer $NewName; "Renamed to $NewName. RESTART needed." }
"--- verify ---"
powercfg /query SCHEME_CURRENT SUB_BUTTONS LIDACTION | Select-String 'Current'
Get-NetConnectionProfile | ForEach-Object { "$($_.Name): $($_.NetworkCategory)" }
hostname
# secrets, .env and the portal DB live here: admins and SYSTEM only
icacls C:\OfficeServer /inheritance:r /grant:r 'Administrators:(OI)(CI)F' 'SYSTEM:(OI)(CI)F' | Out-Null
