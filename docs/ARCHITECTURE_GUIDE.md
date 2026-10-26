# Running the architecture from the flowchart

## Latest IPFS Desktop compatibility correction

Strict `--offline` mode breaks Desktop's bandwidth-based connectivity check. The project now uses a separately managed, isolated private node and Desktop's remote-API controller. Storage is still `.ipfs-local` on loopback API5002; Desktop's API pointer is `.ipfs-desktop-control`. Start the project service first, then Desktop. A swarm key, no listeners/bootstrap peers, disabled discovery/routing/public auto-configuration and zero connected peers preserve isolation. The original strict-offline setup described in historical setup sections below has been superseded; see `ipfs/DESKTOP_SETUP.md` for current operation.

## What has been added

`train_architecture.py` is the new experiment entry point. It uses the unchanged ResNet-18/FedProx local loss and optimizer from `fedprox_core.py`, then applies the separately declared peer policy. `train_fedprox.py` and its existing checkpoint remain the earlier prototype.

The complete implemented round sequence is:

1. Read the prior global checkpoint CID/digest from Hardhat.
2. Three dedicated hospital processes retrieve/verify that global checkpoint from local IPFS and train concurrently.
3. Each hospital saves its own `local_model.pt`, pins it in IPFS, and submits its CID/digest, sample count and input-global digest using its own local development account.
4. Both other hospitals retrieve that candidate and evaluate it and the incoming global model on their own validation partitions. Each peer signs its decision on-chain. Confusion counts allow the contract to compute the declared balanced-accuracy comparison without floating-point ambiguity.
5. The coordinator checks policy/contract agreement, retrieves only accepted checkpoints from IPFS and aggregates with the declared sample-count × peer-score weights. Rejected updates and peer decisions remain in the audit records.
6. If all candidates are rejected, preserve the incoming global bytes and record the no-update round.
7. Pin the new global checkpoint in IPFS, publish its CID/digest and aggregation-evidence digest on-chain, retrieve it for pooled validation selection, and use it as the hospitals' next input.

`blockchain/contracts/FederatedProtocolRegistry.sol` implements this protocol. It is a separate deployment from the final-checkpoint-only `ModelRegistry.sol`. It requires distinct hospital signers and forbids self-review/duplicate reviews, stale parents and out-of-order rounds. It does not prove that reported scores or aggregation calculations are honest. The aggregation evidence is retained locally and its digest is recorded on-chain.

## Setup already performed

- Pinned Kubo 0.43.1 installed under `.tools/kubo`, with the official release checksum verified.
- Isolated project IPFS repo `.ipfs-local`; daemon uses `--offline`, no swarm listeners/bootstrap peers, and loopback API `127.0.0.1:5002`. The pre-existing IPFS service on port 5001 is unrelated and is not used.
- New protocol contract compiled with pinned solc 0.8.30 and deployed to Hardhat chain 31337. Its deployment metadata is `blockchain/deployment.protocol.local.json`.
- Three hospital data manifests and a readiness report were generated under `architecture_preparation/`; images were neither copied nor modified. Hospital validation patients are disjoint, use only the original validation split, and both classes are required.

Hardhat was no longer running and was restarted during setup. Its old in-memory model registration is not live in the new instance; historical receipts and the original trained checkpoint remain preserved. No claim of persistent Ethereum history across Hardhat restarts is made.

## Starting after a machine restart

Update: IPFS Desktop now manages the project offline repository. Open IPFS Desktop instead of launching a separate IPFS daemon, then prepare/inspect the project as below. See `ipfs/DESKTOP_SETUP.md`. The standalone IPFS start command below is only an alternative if Desktop is not managing the repo; never run both.

Use the VS Code integrated PowerShell terminal at `D:\dataset`:

```powershell
.\.venv_runtime\Scripts\python.exe architecture_services.py hardhat
.\.venv_runtime\Scripts\python.exe architecture_services.py ipfs
.\.venv_runtime\Scripts\python.exe -m blockchain.protocol_chain deploy
.\.venv_runtime\Scripts\python.exe prepare_architecture.py
```

The service launcher refuses to create a duplicate when a port is occupied. The adapters additionally check the actual Hardhat instance/contract bytecode and the actual IPFS repo identity. An unknown listener is not accepted as the project service. Services are local background processes; their logs and PID records are under `blockchain/` and `ipfs/`. No PowerShell execution-policy change is required for these Python commands.

Recompile after editing Solidity using the local runtime listed in `.tools/node-runtime.json`:

```powershell
& '.\.tools\node-v22.23.3-win-x64\node.exe' '.\blockchain\compile.cjs'
```

The compiler keeps the original ModelRegistry settings and uses the IR pipeline for the larger protocol contract. Do not edit a contract during an active experiment or overwrite deployment metadata to disguise a reset.

## Starting the new experiment

Training has **not** been started for this architecture. Announce the runtime budget before launch; the earlier prototype's duration is not a measured estimate for this larger loop. Actual parallel GPU fit is also unmeasured. Each of the three workers has a 28% GPU allocator limit. A memory/resource failure stops and preserves the run; there is no automatic sequential fallback or reduction of batch size/rounds/epochs.

When a new architecture run is authorized, run this visibly in VS Code:

```powershell
.\.venv_runtime\Scripts\python.exe -u train_architecture.py
```

The fixed initial protocol is seed 42, 20 rounds, 3 local epochs, mu 0.01, all three hospitals and workers=0 per DataLoader. Local random streams are `42 + (round-1)*3 + hospital_id`; they differ from sequential process RNG order. This is a separately identified experiment. The source/config/manifest digests are frozen in each run configuration. The test split and external dataset are never loaded.

The same OS training lock prevents simultaneous prototype and architecture training, and sleep is inhibited while the new trainer runs. Keep the laptop plugged in and the lid open. Reserve at least 15 GiB for local artifacts/IPFS pins. There is no exact resume implementation; optimizer/RNG state across an interrupted run is not restored. Failed runs remain visible and must not be silently discarded or restarted as if continuous.

## Artifacts

```text
architecture_outputs/run_.../
  run_config.json, policy.json, run_identity.json, execution.json, console.log
  partition_summary.json
  hospitals/hospital_0/  (and hospital_1, hospital_2)
    data_manifest.json
    round_0001/
      incoming_global.pt, local_model.pt, update.json, training.log
      review_baseline.pt, peer_*.pt, review_of_*.json
  rounds/round_0001/
    update_*_receipt.json, review_*_receipt.json
    decisions.json, aggregation.json, accepted/hospital_*.pt
    global.json, global_receipt.json, global_retrieved.pt
  global_round_0000.pt, global_round_0001.pt, ...
  best_model.pt, latest_model.pt, selection.json
  validation_metrics.json, history.csv, best_global_reference.json
```

Every round is retained, including all-rejected rounds. The best checkpoint is chosen on pooled validation balanced accuracy over the unchanged validation union. Successful runs copy reporting metadata under `multiseed_outputs/architecture/` without relabeling historical prototype results.

In a no-update round, the checkpoint bytes (including their embedded creation round) are retained exactly. `selection.json` and `best_global_reference.json` separately record the round at which that global state was selected; it may differ from the embedded creation round.

After a completed architecture run, verify the selected checkpoint:

```powershell
.\.venv_runtime\Scripts\python.exe verify_architecture.py --run-dir architecture_outputs\YOUR_RUN
```

Then use `predict.py --checkpoint ...\best_model.pt --image ...` with a user-selected chest X-ray. Hash verification must precede claiming a checkpoint matches the registered model. IPFS retrieval verifies the registered SHA-256 as well as using a CID. The CID and SHA-256 are distinct identifiers.

## What is not established

The contract compiled and deployed, service identities/configuration were inspected, manifests were prepared, and Python syntax was parsed. No end-to-end run, contract test suite, policy tests, model transport test or three-worker GPU training run was executed. Parallel execution is implemented in code but has not been exercised. No new accuracy results exist for this architecture.

This remains a simulation on one laptop with a shared filesystem, local unlocked accounts, one coordinator and one offline IPFS node. Per-hospital manifests/processes are not operating-system privacy boundaries. Existing non-IID training allocations are retained; a patient's training images can occur at different simulated hospitals, while validation patients are separate from training and one another. IPFS pins persist in the local repo, but Hardhat registrations disappear when that node restarts. External hospital deployment, wallet security, adversarial robustness, privacy guarantees and clinical validity are not implemented or demonstrated.

Repeated peer-validation use can overfit the development set; retain the completely new dataset for independent final evaluation. Protocol decisions and limitations are in `PROTOCOL_DECISIONS.md`.

References: [Kubo RPC API](https://docs.ipfs.tech/reference/kubo/rpc/), [Hardhat local node](https://hardhat.org/docs/guides/hardhat-node).
