# Run as Administrator BEFORE phase4 if "py --version" says it is missing. Installs Python 3.12 for all users, with the py launcher.
$ErrorActionPreference = 'Stop'
if (Get-Command py -ErrorAction SilentlyContinue) { "Python already there: $(py --version)"; return }
$exe = "$env:TEMP\python-3.12.10-amd64.exe"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $exe
Start-Process $exe -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1 Include_test=0' -Wait
"--- verify (open a NEW PowerShell window if this says not found) ---"
& "$env:ProgramFiles\Python312\python.exe" --version
