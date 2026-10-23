# Phase 3 (Administrator), AFTER the user installed SQL Server 2022 Express (instance SQLEXPRESS, mixed auth).
# Sets TCP static port 1433 and a Private+LocalSubnet firewall rule.
$ErrorActionPreference = 'Stop'
$inst = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL').SQLEXPRESS
$tcp = "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\$inst\MSSQLServer\SuperSocketNetLib\Tcp"
Set-ItemProperty $tcp Enabled 1
Set-ItemProperty "$tcp\IPAll" TcpDynamicPorts ''
Set-ItemProperty "$tcp\IPAll" TcpPort '1433'
Restart-Service 'MSSQL$SQLEXPRESS' -Force
sqlcmd -S .\SQLEXPRESS -E -b -Q "IF SUSER_ID(N'NT AUTHORITY\SYSTEM') IS NULL CREATE LOGIN [NT AUTHORITY\SYSTEM] FROM WINDOWS; ALTER SERVER ROLE sysadmin ADD MEMBER [NT AUTHORITY\SYSTEM]"   # the 23:00 backup runs as SYSTEM
if ($LASTEXITCODE) { throw 'could not grant SYSTEM sysadmin; run this as the account that installed SQL' }
if (-not (Get-NetFirewallRule 'Office SQL 1433' -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName 'Office SQL 1433' -Direction Inbound -Protocol TCP -LocalPort 1433 -Profile Private -RemoteAddress LocalSubnet -Action Allow | Out-Null
}
"--- verify ---"
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -match '^(192|10|172)\.' | Select-Object -First 1).IPAddress
Test-NetConnection $ip -Port 1433 | Select-Object TcpTestSucceeded
