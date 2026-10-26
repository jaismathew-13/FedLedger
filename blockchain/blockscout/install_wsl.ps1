$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$log = Join-Path $repo 'RUN_LOG.md'
$output = Join-Path $PSScriptRoot 'wsl-install.log'
Add-Content $log "`n$([DateTime]::UtcNow.ToString('o')) Begin elevated wsl.exe --install --no-distribution --no-launch; no reboot requested."
try {
    & wsl.exe --install --no-distribution --no-launch 2>&1 | Out-File $output -Encoding utf8
    $result = $LASTEXITCODE
    Add-Content $log "$([DateTime]::UtcNow.ToString('o')) WSL install ended, exit=$result; output blockchain/blockscout/wsl-install.log. Windows may require restart; this script never restarts."
    exit $result
} catch {
    Add-Content $log "$([DateTime]::UtcNow.ToString('o')) WSL installation error: $_"
    throw
}
