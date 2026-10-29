# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Verify the actual blockchain independently of the dashboard

The running blockchain is a local Hardhat Ethereum development node. The dashboard queries it through JSON-RPC. The commands below query that node directly using PowerShell; they do not call the dashboard or read its saved reports.

Open a new **VS Code PowerShell terminal**. Keep the existing system running. Do not launch another Hardhat node or use `--fresh-chain` during the demonstration.

## 1. Identify the running node

```powershell
$rpc = 'http://127.0.0.1:8545'
Invoke-RestMethod -Uri $rpc -Method Post -ContentType 'application/json' -Body '{"jsonrpc":"2.0","id":1,"method":"web3_clientVersion","params":[]}' | ConvertTo-Json -Depth 10
```

The result identifies HardhatNetwork. This response comes from port8545, not the dashboard on8765.

## 2. Read a live block, including its transactions

```powershell
$liveBlock = Invoke-RestMethod -Uri $rpc -Method Post -ContentType 'application/json' -Body '{"jsonrpc":"2.0","id":2,"method":"eth_getBlockByNumber","params":["latest",true]}'
$liveBlock | ConvertTo-Json -Depth 30
```

Inspect `number`, `hash`, `parentHash`, `timestamp`, and `transactions`. Ethereum JSON-RPC represents many numeric fields in hexadecimal. For example, `0xc` is block12. Convert the current number if desired:

```powershell
[Convert]::ToInt64($liveBlock.result.number.Substring(2), 16)
```

For a specific block, replace `"latest"` with its hexadecimal number. Examples: `"0x4"` for block4, `"0x8"` for8, `"0xa"` for10, `"0xb"` for11.

## 3. Read the actual transaction receipt

When the displayed block contains at least one transaction:

```powershell
$transactionHash = $liveBlock.result.transactions[0].hash
$receiptRequest = @{ jsonrpc = '2.0'; id = 3; method = 'eth_getTransactionReceipt'; params = @($transactionHash) } | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri $rpc -Method Post -ContentType 'application/json' -Body $receiptRequest | ConvertTo-Json -Depth 30
```

Compare `transactionHash`, `blockHash` and `blockNumber` with the block and dashboard. Receipt status `0x1` means success, `0x0` means failure. Contract event logs appear under `logs`; the dashboard decodes these raw events into hospital approval and client-authorization labels.

## 4. Watch the node's own log in another terminal

```powershell
cd D:\dataset
Get-Content .\blockchain\chain.stdout.log -Tail 30 -Wait
```

This displays the Hardhat process's own RPC/mining log. Press Ctrl+C to stop the log viewer; the node remains running. Historical log text alone is not live chain verification; use the RPC queries above as well.

## Suggested judge demonstration

1. Query the current latest block using PowerShell.
2. Submit a genuine hospital approval or client authorization through the normal portal workflow.
3. Repeat the PowerShell query and inspect the new transaction receipt.
4. Show the matching block/transaction hashes in the dashboard.

An application submission alone is local; approval is the step that creates the hospital membership transaction. Use a planned demonstration application rather than altering a training participant's state during a campaign.

The judge can type or modify these RPC requests independently. No custom Python display script is required. These are genuine local development-chain blocks; this does not establish a public deployment or institutional decentralization. Public Etherscan does not index this localhost node. A standalone third-party explorer would be another viewer of the same node.

Hardhat state is ephemeral. A node reset creates a different chain instance, even when chain ID31337 and contract addresses repeat. Old archived receipts must be presented as historical evidence.

## One-command raw viewer / live demonstration

From a new VS Code PowerShell terminal:

```powershell
cd D:\dataset
powershell -NoProfile -ExecutionPolicy Bypass -File .\blockchain\verify_live_chain.ps1 -Watch
```

This prints raw node responses for the latest tip and its receipts whenever the tip changes. It polls read-only JSON-RPC methods at localhost:8545; it does not use the dashboard, SQLite, saved receipt files or private keys. It is a tip viewer, not a complete historical indexing service. Leave it visible while performing a planned approval in the portal. Press Ctrl+C to stop only the viewer.

For one specific block:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\blockchain\verify_live_chain.ps1 -Block 12
```

The process-only Bypass option allows this local script to run without changing Windows' saved execution policy. Inspect the script or use the direct Invoke-RestMethod commands above if preferred. The script permits only read methods and checks that receipt hashes match the block. It stops if the Hardhat instance changes. No new transactions are created by this viewer.
