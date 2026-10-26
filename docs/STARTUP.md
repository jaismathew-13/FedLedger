# Starting the local system after restarting Windows

Open VS Code, open D:\dataset, and choose Terminal > New Terminal (PowerShell).

After a laptop reboot, run:

```powershell
cd D:\dataset
.\.venv_runtime\Scripts\python.exe start_local_system.py --fresh-chain
```

This authorizes a new ephemeral development chain if the recorded one is missing or replaced. Old deployment references, service logs and the enrollment database are archived first. New contracts are deployed. Existing hospital applications/data stay local, but previously approved hospitals become pending and client delegation must be signed again. Old transactions remain historical and are not restored. Completed/cancelled campaigns are preserved as historical records after verifying execution status. Unfinished campaigns still block automatic replacement. The launcher uses the saved execution status, even if the database still shows an earlier UI command.

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
Runtime verification is pending until Windows is restarted and Docker is running.
