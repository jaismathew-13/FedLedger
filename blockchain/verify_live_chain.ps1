param(
    [ValidateRange(-1,2147483647)][long]$Block = -1,
    [switch]$Watch,
    [ValidateRange(1,60)][int]$PollSeconds = 2
)

# Read-only JSON-RPC. No dashboard APIs, local receipt files, keys or transactions.
$ErrorActionPreference = 'Stop'
$rpcAddress = 'http://127.0.0.1:8545'
$script:rpcRequestId = 0

function Read-NodeRpc {
    param([string]$Method, [object[]]$RpcParams = @())
    $allowed = @('web3_clientVersion','eth_chainId','hardhat_metadata','eth_blockNumber',
                 'eth_getBlockByNumber','eth_getTransactionReceipt')
    if ($Method -notin $allowed) { throw 'Only read-only RPC methods are permitted.' }
    $script:rpcRequestId++
    $request = @{ jsonrpc = '2.0'; id = $script:rpcRequestId; method = $Method; params = @($RpcParams) }
    $response = Invoke-RestMethod -Uri $rpcAddress -Method Post -ContentType 'application/json' `
        -Body ($request | ConvertTo-Json -Depth 10) -TimeoutSec 10
    if ($response.error) { throw ($response.error | ConvertTo-Json -Compress) }
    return $response
}

if ($Watch -and $Block -ge 0) { throw 'Use -Watch for the latest tip, or -Block for a specific block.' }

Write-Host "Direct node endpoint: $rpcAddress" -ForegroundColor Cyan
Read-NodeRpc -Method 'web3_clientVersion' | ConvertTo-Json -Depth 10
$chain = Read-NodeRpc -Method 'eth_chainId'
$chain | ConvertTo-Json -Depth 10
if ($chain.result -ne '0x7a69') { throw 'Expected local development chain ID 31337.' }
$identity = (Read-NodeRpc -Method 'hardhat_metadata').result.instanceId
if (-not $identity) { throw 'Expected a running Hardhat node.' }
Write-Host "Chain instance: $identity" -ForegroundColor Cyan
if ($Watch) { Write-Host 'Watching the latest block tip. Press Ctrl+C to stop this viewer.' }

$lastHash = $null
do {
    if ((Read-NodeRpc -Method 'hardhat_metadata').result.instanceId -ne $identity) {
        throw 'Hardhat chain instance changed. Viewer stopped to avoid mixing different chains.'
    }
    $tag = if ($Block -ge 0) { '0x' + $Block.ToString('x') } else { 'latest' }
    $blockResponse = Read-NodeRpc -Method 'eth_getBlockByNumber' -RpcParams @($tag,$true)
    $current = $blockResponse.result
    if (-not $current) { throw 'Requested block is not present on the current chain.' }
    if ($current.hash -ne $lastHash) {
        Write-Host 'RAW BLOCK RESPONSE' -ForegroundColor Green
        $blockResponse | ConvertTo-Json -Depth 30
        foreach ($transaction in $current.transactions) {
            $receiptResponse = Read-NodeRpc -Method 'eth_getTransactionReceipt' -RpcParams @($transaction.hash)
            $receipt = $receiptResponse.result
            if (-not $receipt -or $receipt.blockHash -ne $current.hash -or $receipt.transactionHash -ne $transaction.hash) {
                throw 'Receipt does not match the queried block and transaction.'
            }
            Write-Host 'RAW TRANSACTION RECEIPT RESPONSE' -ForegroundColor Green
            $receiptResponse | ConvertTo-Json -Depth 30
        }
        if ((Read-NodeRpc -Method 'hardhat_metadata').result.instanceId -ne $identity) {
            throw 'Node reset during verification. Treat this sample as invalid.'
        }
        $lastHash = $current.hash
    }
    if ($Watch) { Start-Sleep -Seconds $PollSeconds }
} while ($Watch)
