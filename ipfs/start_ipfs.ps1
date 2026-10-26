# Start the configured project IPFS service (strict offline or isolated private mode).
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $projectRoot '.venv_runtime/Scripts/python.exe') (Join-Path $projectRoot 'architecture_services.py') ipfs
if ($LASTEXITCODE -ne 0) { throw 'Project IPFS service did not start.' }
