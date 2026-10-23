# Nightly job (SYSTEM, 23:00). Writes backup-status.json for the portal status page.
param([string]$BackupDrive = 'E:', [string]$DataRoot = $(if (Test-Path D:\) { 'D:\OfficeData' } else { 'C:\OfficeData' }))
$R = 'C:\OfficeServer'; $status = "$R\logs\backup-status.json"
function Done($ok, $msg) {
  @{ ok = $ok; time = [DateTimeOffset]::Now.ToUnixTimeSeconds(); message = $msg } | ConvertTo-Json | Set-Content $status -Encoding UTF8
  if (-not $ok) { exit 1 }
}
try {
  if (-not (Test-Path "$BackupDrive\")) { Done $false "Drive $BackupDrive not found" }
  $day = Get-Date -Format 'yyyy-MM-dd'
  $local = Join-Path (Split-Path $DataRoot) 'Backups\SQL'
  New-Item -ItemType Directory -Force $local, "$BackupDrive\OfficeBackup\SQL\$day" | Out-Null
  if (Get-Service 'MSSQL$SQLEXPRESS' -ErrorAction SilentlyContinue) {
    $dbs = (sqlcmd -S .\SQLEXPRESS -E -h -1 -W -b -Q "SET NOCOUNT ON; SELECT name FROM sys.databases WHERE database_id>4") | Where-Object { $_ }
    if ($LASTEXITCODE) { Done $false "SQL: cannot list databases" }
    foreach ($d in $dbs) {
      sqlcmd -S .\SQLEXPRESS -E -b -Q "BACKUP DATABASE [$d] TO DISK=N'$local\$d.bak' WITH INIT"
      if ($LASTEXITCODE) { Done $false "SQL backup failed: $d" }
    }
    Copy-Item "$local\*.bak" "$BackupDrive\OfficeBackup\SQL\$day" -Force
    Get-ChildItem "$BackupDrive\OfficeBackup\SQL" -Directory | Sort-Object Name -Descending | Select-Object -Skip 7 | Remove-Item -Recurse -Force
  }
  robocopy $DataRoot "$BackupDrive\OfficeBackup\Data" /MIR /R:2 /W:5 /XD "$DataRoot\.tmp" /NFL /NDL /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { Done $false "robocopy error $LASTEXITCODE" }
  New-Item -ItemType Directory -Force "$BackupDrive\OfficeBackup\Portal" | Out-Null
  Copy-Item "$R\portal\portal.db" "$BackupDrive\OfficeBackup\Portal\portal.db" -Force   # shortcut: plain copy of a small DB
  Done $true "OK"
} catch { Done $false $_.Exception.Message }
