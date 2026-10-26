# Standalone blockchain explorer: Blockscout

## Status

Docker Desktop and WSL3.0.3 are installed. Docker Compose accepted the configuration.
Windows requires a restart to activate WSL; the Docker engine and explorer are not
running. Runtime verification remains pending. Do not present the explorer as working
merely because these configuration files exist. Current status is recorded in
`multiseed_outputs/blockscout/setup_status.json`.

This is the standard Blockscout frontend and backend, independent of our dashboard.
It reads the existing local Hardhat node at `http://127.0.0.1:8545`, chain31337.
It cannot show public Ethereum transactions, and the local chain is a prototype.

## First installation

The signed Docker installer is downloaded into `.tools/installers/` during setup.
WSL installation is requested through an administrator prompt without installing
Ubuntu and without restarting automatically. If Windows says a restart is needed,
save your work first. A restart stops this project's ephemeral Hardhat node; raw
archived block/receipt evidence does not restore a node's mutable state.

Open Docker Desktop after installation, review/accept its terms yourself, and finish
any WSL setup it requests. Wait until the Docker engine is running. If installation
was interrupted, consult `blockchain/blockscout/wsl-install.log` and `RUN_LOG.md`.

## Start

Start the project's normal local services first, following [STARTUP.md](STARTUP.md).
Do not reset an already-running chain just to start Blockscout.

In the VS Code PowerShell terminal:

```powershell
cd D:\dataset
powershell -NoProfile -ExecutionPolicy Bypass -File .\blockchain\blockscout\start.ps1
```

The first container image download may take10–20minutes. The script records the
Hardhat instance ID, archives all current blocks and receipts to
`multiseed_outputs/blockscout/`, and starts only explorer containers. It never starts
training or submits blockchain transactions.

Once ready, open **http://localhost:4000**. Choose Blocks to view the chain from
genesis and Transactions to inspect receipts. Search for the current HospitalDirectory
contract address from `blockchain/deployment.directory.local.json` to inspect hospital
authorization transaction logs. An unverified contract may display raw log topics
and data rather than friendly event names. Registration applications in the local
database do not create chain transactions until an authorization action is recorded.
Hospital registration does not upload a model to IPFS.

The launcher uses a database volume per Hardhat instance, so a fresh chain cannot
silently reuse an old explorer index. If the instance changed, stop the old explorer,
archive `blockchain/blockscout/local-state.json`, and start a separate index. The old
database volumes remain preserved. Never run `docker compose down -v` to troubleshoot.

## Status and logs

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\blockchain\blockscout\start.ps1 -Action status
powershell -NoProfile -ExecutionPolicy Bypass -File .\blockchain\blockscout\start.ps1 -Action logs
```

An nginx502 response during startup usually means backend migrations or the frontend
are still starting. Persistent failures need container logs. If logs show RPC connection
failures, verify Docker can reach `host.docker.internal:8545`; do not restart or expose
Hardhat to the LAN as an automatic workaround.

## Stop explorer only

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\blockchain\blockscout\start.ps1 -Action stop
```

This preserves its database and leaves Hardhat, IPFS and the project dashboard running.
Only the explorer HTTP port is published, bound to loopback. No PostgreSQL/Redis ports
are exposed. Local generated credentials are excluded from Git.

## Verify before the demonstration

Compare `http://localhost:4000/api/v2/blocks` and a transaction's receipt/block hash
with the direct node output:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\blockchain\verify_live_chain.ps1 -Block 12
```

Use a block that exists on the current instance. Check both hashes match. Record the
live container image digests and results under `multiseed_outputs/blockscout/`.

References: [official Blockscout Docker configuration](https://github.com/blockscout/blockscout/tree/9cd48cc0708d520f093ec8a8c37d9a998b258171/docker-compose),
[Docker Windows installation](https://docs.docker.com/desktop/setup/install/windows-install/),
[Microsoft WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).
