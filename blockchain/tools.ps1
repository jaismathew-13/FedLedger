param([ValidateSet('compile','chain','versions')][string]$Action = 'versions')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeInfo = Get-Content -LiteralPath (Join-Path $projectRoot '.tools/node-runtime.json') -Raw | ConvertFrom-Json
$nodeDirectory = Join-Path $projectRoot ('.tools/' + $runtimeInfo.folder)
$nodeExecutable = Join-Path $nodeDirectory 'node.exe'
$npmScript = Join-Path $nodeDirectory 'node_modules/npm/bin/npm-cli.js'
$oldPath = $env:PATH
try {
    $env:PATH = $nodeDirectory + [IO.Path]::PathSeparator + $oldPath
    Push-Location -LiteralPath $PSScriptRoot
    try {
        Add-Content -LiteralPath (Join-Path $projectRoot 'RUN_LOG.md') -Value "`n$([DateTime]::UtcNow.ToString('o')) blockchain/tools.ps1 $Action start."
        if ($Action -eq 'versions') {
            & $nodeExecutable --version
            & $nodeExecutable $npmScript --version
        } else {
            & $nodeExecutable $npmScript run $Action
        }
        $toolExit = $LASTEXITCODE
        Add-Content -LiteralPath (Join-Path $projectRoot 'RUN_LOG.md') -Value "$([DateTime]::UtcNow.ToString('o')) blockchain/tools.ps1 $Action end; exit=$toolExit."
        if ($toolExit -ne 0) { throw "Blockchain tool failed with exit $toolExit" }
    } finally { Pop-Location }
} finally { $env:PATH = $oldPath }
