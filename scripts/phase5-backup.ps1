# Phase 5 (Administrator): schedule the 23:00 job and run it once.
param([string]$BackupDrive = 'E:')
$a = New-ScheduledTaskAction -Execute powershell.exe -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\OfficeServer\scripts\backup-job.ps1 -BackupDrive $BackupDrive"
Register-ScheduledTask OfficeBackup -Action $a -Trigger (New-ScheduledTaskTrigger -Daily -At 23:00) -User SYSTEM -RunLevel Highest -Force | Out-Null
Start-ScheduledTask OfficeBackup
Start-Sleep 20
Get-Content C:\OfficeServer\logs\backup-status.json
