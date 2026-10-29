# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Starting the local system after restarting Windows

Open VS Code, open D:\dataset, and choose Terminal > New Terminal (PowerShell).

After a laptop reboot, run:

```powershell
cd D:\dataset
.\.venv_runtime\Scripts\python.exe start_local_system.py --fresh-chain
```

This authorizes a new ephemeral development chain if the recorded one is missing or replaced. Old deployment references, service logs and the enrollment database are archived first. New contracts are deployed. Existing hospital applications/data stay local, but previously approved hospitals become pending and client delegation must be signed again. Old transactions remain historical and are not restored. Completed, cancelled and failed campaigns are preserved as historical records after verifying execution status. Failed attempts retain their error/history; they do not block a new chain indefinitely. Unfinished campaigns still block automatic replacement. The launcher uses the saved execution status, even if the database still shows an earlier UI command.

If the same chain is still running, use:

```powershell
cd D:\dataset
.\.venv_runtime\Scripts\python.exe start_local_system.py
```

Matching running services are reused. Keep the dashboard terminal open. This command does not start model training.

Open:

- Admin: http://127.0.0.1:8765/admin
- Hospital: http://127.0.0.1:8765/hospital
- IPFS Web UI: http://127.0.0.1:5002/webui
- IPFS Desktop API address: http://127.0.0.1:5002
- Hardhat RPC: http://127.0.0.1:8545, chain ID 31337

IPFS Desktop is optional for the training storage API. Start Desktop separately if you want its Files interface. Zero peers is expected for the project's isolated IPFS configuration.

Python and Node are already installed locally. Environment activation and reinstalling packages are unnecessary. Start training separately using the registered campaign command in a visible VS Code terminal.

## Optional independent blockchain explorer

Blockscout requires Docker Desktop with a running Linux engine. After starting the
project services, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\blockchain\blockscout\start.ps1
```

Open http://localhost:4000 when the explorer is ready. See [BLOCKSCOUT.md](BLOCKSCOUT.md)
for installation and preserving explorer indexes when the Hardhat instance changes.
Runtime was verified on27October2026; see multiseed_outputs/blockscout/live_verification.json. Docker Desktop must be running for the explorer.

## Startup safeguards and interrupted deployment

The fresh-chain path validates all three contracts and the client-authorization directory dependency. It refuses a non-Hardhat RPC service, reuses an already matching chain, and takes the same OS lock used by training before any migration. Running, paused, or other unfinished campaigns still block replacement. A completed campaign must have every registered round in sequence.

Before replacing deployment references, startup backs up SQLite, contract references, logs and campaign JSON. An atomic migration journal records progress. If a contract deployment or enrollment reset fails, preserve the node and rerun the same `--fresh-chain` command; it verifies the backup and resumes on that instance. If the node itself was lost again, the old partial attempt is archived before a separate replacement. Datasets, model files, local agent keys and registered data manifests stay in place; old signatures/approvals and wallet sessions are cleared for the new chain.

Isolated startup checks: `.\.venv_runtime\Scripts\python.exe check_fresh_chain_startup.py`. These use mocked services/RPC and separate SQLite/files; they do not reset your running chain. Results: `multiseed_outputs/fresh_chain_startup_checks.json`.
