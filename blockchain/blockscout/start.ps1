param(
    [ValidateSet('start','stop','status','logs')][string]$Action = 'start',
    [ValidateRange(1024,65535)][int]$Port = 4000
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$log = Join-Path $repo 'RUN_LOG.md'
$stateFile = Join-Path $PSScriptRoot 'local-state.json'
function Log([string]$Message) {
    Add-Content $log "`n$([DateTime]::UtcNow.ToString('o')) Blockscout: $Message"
}
function Rpc([string]$Method, [object[]]$Parameters = @()) {
    $body = @{jsonrpc='2.0'; id=1; method=$Method; params=$Parameters} | ConvertTo-Json -Depth 30 -Compress
    $response = Invoke-RestMethod http://127.0.0.1:8545 -Method Post -ContentType application/json -Body $body -TimeoutSec 15
    if ($response.error) { throw ($response.error | ConvertTo-Json -Compress) }
    return $response.result
}
try {
    Log "command start.ps1 -Action $Action -Port $Port began."
    $docker = (Get-Command docker.exe -ErrorAction SilentlyContinue).Source
    if (-not $docker) {
        foreach ($candidate in @(
            "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe",
            "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe"
        )) { if (Test-Path -LiteralPath $candidate) { $docker = $candidate; break } }
    }
    if (-not $docker) { throw 'Docker Desktop is not installed. See docs/BLOCKSCOUT.md.' }
    & $docker info --format '{{.ServerVersion}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine is unavailable. Open Docker Desktop and finish WSL/restart setup first.' }
    if ($Action -eq 'start') {
        $chain = Rpc 'eth_chainId'
        if ($chain -ne '0x7a69') { throw "Expected local Hardhat chain31337; received $chain" }
        $metadata = Rpc 'hardhat_metadata'
        if (-not $metadata.instanceId) { throw 'Hardhat instance identity is missing.' }
        $identity = $metadata.instanceId -replace '^0x',''
        $project = 'hospital-blockscout-' + $identity.Substring(0,12).ToLowerInvariant()
        $envFile = Join-Path $PSScriptRoot "$project.env"
        if (-not (Test-Path -LiteralPath $envFile)) {
            $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
            $bytes = New-Object byte[] 64
            $rng.GetBytes($bytes)
            $secret = [Convert]::ToBase64String($bytes)
            $rng.GetBytes($bytes)
            $password = ([BitConverter]::ToString($bytes[0..23])).Replace('-','').ToLowerInvariant()
            $rng.Dispose()
            @("EXPLORER_PORT=$Port", "DB_PASSWORD=$password", "SECRET_KEY_BASE=$secret") | Set-Content -LiteralPath $envFile -Encoding ascii
        } else {
            $savedPort = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^EXPLORER_PORT=' }
            if ($savedPort -ne "EXPLORER_PORT=$Port") { throw 'This chain already has an explorer with a different port. Use its original port.' }
        }
        if (Test-Path -LiteralPath $stateFile) {
            $previous = Get-Content -Raw -LiteralPath $stateFile | ConvertFrom-Json
            if ($previous.project -ne $project) {
                throw 'Hardhat instance changed. The previous explorer index is preserved. Stop its stack with -Action stop before archiving local-state.json and starting an independent index.'
            }
        }
        $state = @{project=$project;instance_id=$metadata.instanceId;chain_id=31337;port=$Port;env_file=$envFile;started_utc=[DateTime]::UtcNow.ToString('o');verified=$false}
        $state | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding utf8
        # Read-only snapshot preserves evidence even if the ephemeral node later stops.
        $height = [Convert]::ToInt32((Rpc 'eth_blockNumber').Substring(2),16)
        $blocks = @()
        for ($number=0; $number -le $height; $number++) {
            $block = Rpc 'eth_getBlockByNumber' @(('0x{0:x}' -f $number), $true)
            $receipts = @()
            foreach ($tx in $block.transactions) { $receipts += Rpc 'eth_getTransactionReceipt' @($tx.hash) }
            $blocks += @{block=$block;receipts=$receipts}
        }
        $evidence = Join-Path $repo 'multiseed_outputs\blockscout'
        New-Item -ItemType Directory -Force -Path $evidence | Out-Null
        @{captured_utc=[DateTime]::UtcNow.ToString('o');metadata=$metadata;blocks=$blocks} | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $evidence "$project-chain.json") -Encoding utf8
        Log "Read-only chain snapshot captured through block $height; no transactions sent. Initial image download/start can take 10-20 minutes."
    } else {
        if (-not (Test-Path -LiteralPath $stateFile)) { throw 'Explorer has not been started yet.' }
        $state = Get-Content -Raw -LiteralPath $stateFile | ConvertFrom-Json
        $project = $state.project
        $envFile = $state.env_file
    }
    $compose = @('compose','--project-name',$project,'--env-file',$envFile,'-f',(Join-Path $PSScriptRoot 'compose.yaml'))
    if ($Action -eq 'start') {
        & $docker @compose config --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Docker Compose configuration validation failed.' }
        & $docker @compose up -d
        if ($LASTEXITCODE -ne 0) { throw 'Blockscout container launch failed. Run -Action logs for details.' }
        Write-Host "Blockscout is starting at http://localhost:$Port (indexing may take several minutes)."
        Log "Compose up completed. URL http://localhost:$Port; indexing/API not yet verified."
    } elseif ($Action -eq 'stop') {
        & $docker @compose stop
    } elseif ($Action -eq 'status') {
        & $docker @compose ps
    } else {
        & $docker @compose logs --tail 80
    }
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed with exit $LASTEXITCODE" }
    Log "command completed ($Action)."
} catch {
    Log "ERROR: $_"
    throw
}
