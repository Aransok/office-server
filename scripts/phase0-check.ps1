# Phase 0: report only, changes nothing.
$os = Get-ComputerInfo -Property WindowsProductName,WindowsVersion,CsTotalPhysicalMemory,CsProcessors
"Windows : $($os.WindowsProductName) $($os.WindowsVersion)"
if ($os.WindowsProductName -match 'Home') { "  !! Home edition: cannot accept Remote Desktop" }
"RAM     : {0:N1} GB" -f ($os.CsTotalPhysicalMemory/1GB)
"CPU     : $($os.CsProcessors.Name)"
Get-PSDrive -PSProvider FileSystem | ForEach-Object { "Drive {0}: {1:N0} GB free" -f $_.Name, ($_.Free/1GB) }
Get-NetAdapter | Where-Object Status -eq Up | ForEach-Object { "NIC     : $($_.Name) ($($_.InterfaceDescription)) MAC $($_.MacAddress)" }
Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -notmatch '^(127|169)' | ForEach-Object { "IP      : $($_.IPAddress) on $($_.InterfaceAlias)" }
Get-NetConnectionProfile | ForEach-Object { "Profile : $($_.Name) = $($_.NetworkCategory)" }
powercfg /getactivescheme
"Defender: $((Get-MpComputerStatus).AntivirusEnabled)"
foreach ($t in 'python','py','git','sqlcmd') {
  $c = Get-Command $t -ErrorAction SilentlyContinue
  "{0,-8}: {1}" -f $t, $(if ($c) { $c.Source } else { 'not found' })
}
Get-Service 'MSSQL*' -ErrorAction SilentlyContinue | ForEach-Object { "SQL svc : $($_.Name) $($_.Status)" }
$apps = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue
$apps | Where-Object { $_.DisplayName -match 'Expecta|Microinvest|Delta|MoneyWorks|STIL|SQL Server' } | ForEach-Object { "App     : $($_.DisplayName)" }
