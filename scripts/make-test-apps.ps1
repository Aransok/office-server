# Run on the server (Administrator): puts a few harmless Windows programs into O:\_Програми so the launcher can be tested.
$dir = Join-Path (Get-SmbShare Office).Path '_Програми'
New-Item -ItemType Directory -Force $dir | Out-Null
$sh = New-Object -ComObject WScript.Shell
@{ 'Notepad' = 'notepad.exe'; 'Calculator' = 'calc.exe'; 'Paint' = 'mspaint.exe'; 'WordPad' = 'write.exe' }.GetEnumerator() | ForEach-Object {
  $tmp = "$env:TEMP\$($_.Key).lnk"   # the COM shortcut API cannot save into a Cyrillic path, so save to an ASCII one and move
  $l = $sh.CreateShortcut($tmp); $l.TargetPath = "$env:SystemRoot\System32\$($_.Value)"; $l.Save()
  Move-Item $tmp "$dir\$($_.Key).lnk" -Force
}
"Created test shortcuts in $dir"
