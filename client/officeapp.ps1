# Opens an app from the server's programs folder. Started by the officeapp: link in the portal.
# Only files under O:\_Програми with a known extension can be started.
param([string]$Uri)
$root = 'O:\_Програми'
try {
  $rel = ''
  if ($Uri -match '[?&]p=([^&]*)') { $rel = [uri]::UnescapeDataString(($Matches[1] -replace '\+', ' ')) }
  if (-not (Test-Path 'O:\')) { throw 'Drive O: is not connected. Run setup.cmd again.' }
  if (-not $rel) { Start-Process explorer 'O:\'; return }
  $full = [IO.Path]::GetFullPath((Join-Path $root $rel))
  if (-not $full.StartsWith("$root\", [StringComparison]::OrdinalIgnoreCase)) { throw 'Not allowed.' }
  if ([IO.Path]::GetExtension($full).ToLower() -notin '.exe', '.lnk', '.bat', '.cmd', '.accdb', '.mdb') { throw 'Not allowed.' }
  if (-not (Test-Path $full -PathType Leaf)) { throw "Not found: $rel" }
  Start-Process -FilePath $full -WorkingDirectory (Split-Path $full)
} catch {
  (New-Object -ComObject WScript.Shell).Popup($_.Exception.Message, 0, 'Office', 48) | Out-Null
}
