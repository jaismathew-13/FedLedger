# Full architecture experiment; run only from the visible VS Code terminal.
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExecutable = Join-Path $projectRoot '.venv_runtime/Scripts/python.exe'
Push-Location -LiteralPath $projectRoot
try {
    Write-Host 'Full architecture: 20 rounds, 3 simultaneous hospital processes, two peer reviews per update.'
    Write-Host 'IPFS and Hardhat must be running. Test set is never loaded.'
    Write-Host 'Runtime is unmeasured and may exceed the earlier prototype. No automatic serial fallback.'
    & $pythonExecutable -u (Join-Path $projectRoot 'train_architecture.py')
    if ($LASTEXITCODE -ne 0) { throw 'Architecture run failed; inspect preserved execution.json/logs. No automatic fresh run started.' }
} finally { Pop-Location }
