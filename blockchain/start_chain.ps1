$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runLog = Join-Path $projectRoot 'RUN_LOG.md'
Add-Content -LiteralPath $runLog -Value "`n$([DateTime]::UtcNow.ToString('o')) start_chain.ps1 start."
# Refuse an occupied port rather than creating duplicate nodes or reusing an unknown service.
$portProbe = [Net.Sockets.TcpClient]::new()
try {
    $portProbe.Connect('127.0.0.1', 8545)
    throw 'Port 8545 is already in use. Run registry.py status to inspect the existing chain.'
} catch [Net.Sockets.SocketException] {
    # No listener; continue.
} finally { $portProbe.Dispose() }
$runtime = Get-Content -LiteralPath (Join-Path $projectRoot '.tools/node-runtime.json') -Raw | ConvertFrom-Json
$nodeExecutable = Join-Path $projectRoot ('.tools/' + $runtime.folder + '/node.exe')
$hardhatCli = Join-Path $PSScriptRoot 'node_modules/hardhat/dist/src/cli.js'
$process = Start-Process -FilePath $nodeExecutable -ArgumentList @($hardhatCli,'node','--hostname','127.0.0.1','--port','8545') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'chain.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'chain.stderr.log') -PassThru
@{ pid = $process.Id; startedUtc = [DateTime]::UtcNow.ToString('o'); endpoint = 'http://127.0.0.1:8545' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'chain-process.json')
Add-Content -LiteralPath $runLog -Value "$([DateTime]::UtcNow.ToString('o')) Started Hardhat 3 node PID=$($process.Id); localhost only; ephemeral chain state; no training."
Write-Output "Started local chain PID $($process.Id). Logs: blockchain/chain.stdout.log and chain.stderr.log"
