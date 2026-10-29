# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Operation and reproducibility

## Existing completed run

```powershell
cd D:\dataset
.\.venv_runtime\Scripts\python.exe start_project.py
```

The launcher checks the original run-bound Hardhat deployment, starts isolated IPFS only if needed, verifies identity, and reuses the matching dashboard or starts it. It does not deploy contracts or run training. If the chain is missing or replaced, it stops with a clear error. Run training only when separately authorized and from a visible VS Code terminal.

## Preserve evidence

Hardhat is an ephemeral local development chain. Do not stop/reset the original node if live verification is needed. A normal restart or reboot does not preserve its original instance. Saved receipts/metadata can be archived as historical evidence but are not a restorable chain snapshot. Never claim that redeployment restores old transactions. No automatic replacement/deployment is performed by start_project.py.

Keep architecture_outputs, multiseed_outputs, the isolated .ipfs-local repo and its private swarm key intact. Keep secrets local; do not publish the repository wholesale. IPFS pin storage and model .pt files require disk backups if long-term retention is needed. MFS references are labels over existing content, not independent backups. Do not change IPFS network isolation for a demo.

## Dependencies

Python: requirements.txt; captured installed versions in requirements-current-lock.txt. Install CUDA PyTorch from the CUDA12.8 wheel index specified by the project runbook. Node runtime is selected in .tools/node-runtime.json; blockchain/package-lock.json records JavaScript dependencies. Do not update dependencies during a final demonstration.

## Failure handling

- Chain disconnected or changed: preserve receipt evidence, do not redeploy over historical metadata; dashboard historical views remain usable.
- IPFS unavailable: start via architecture_services.py ipfs; verify repo identity/isolation before use.
- Wrong dashboard port/run: stop only that dashboard process deliberately, then relaunch the desired run; do not start duplicate services.
- Invalid upload: choose JPEG/PNG/BMP chest X-ray within size limit. Inputs cannot be clinically validated by the software.
- No log output: workers intentionally suppress nested progress; artifact status and execution.json are authoritative, not an empty log.

## Checks and remaining manual step

Run check_project_integration.py for explicitly authorized API integration checks. It uses a synthetic image only for wiring, not accuracy. Tests include accepted/rejected audits, version selection, invalid input and simulated service errors; real services are not intentionally killed. Browser-control inventory was empty, so visual/mobile interaction needs a manual walkthrough using DEMO_GUIDE.md. This is an explicit verification gap.

## Authorized chain replacement, 20 October 2026
The previous node was offline. Its deployment records, logs, a consistent hospital database backup and historical run JSON evidence were archived under `local_operations/chain_archives/20261020T171045Z/`. This is evidence, not a restorable node snapshot. A fresh local chain now serves future operations; its identity is recorded in `local_operations/chain_migration_current.json`. SNRSE authorization was restored with a new receipt. MOSC remains pending. No model was retrained. Historical run receipts cannot be verified against this new chain. `start_project.py` accepts only this explicitly recorded replacement; it still refuses later unknown chain resets.
