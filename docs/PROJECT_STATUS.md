# Project status: full architecture implemented, new run not started

## Latest architecture instruction

The user's flowchart is implemented in a separate `train_architecture.py` entry point: per-hospital checkpoints, IPFS transport, parallel workers, peer reviews, update/global CID records, adaptive aggregation and redistribution. See `ARCHITECTURE_GUIDE.md` for current scope. The new protocol contract is compiled/deployed, isolated offline IPFS is configured on port5002, and hospital manifests/readiness metadata are prepared. No full-architecture training or end-to-end tests have run; parallel GPU fit is unmeasured. Existing checkpoints/results belong to the previous prototype and are preserved. The sections below record prior implementation stages.

## Completed

- ResNet-18/FedProx single-run trainer and best/latest checkpoint saving.
- Single-image prediction command using checkpoint preprocessing and class mapping.
- Local Ethereum dependencies and Hardhat 3.20.0 development chain (ID 31337).
- Solidity ModelRegistry compiled and deployed; ABI/address/receipt persisted in `blockchain/deployment.hardhat.local.json`.
- Python commands for deployment status, publisher access, model-hash registration and verification against actual local artifacts.
- Scientific logs, historical results and patient-split evidence preserved.

## Current scope and limitations

This is a command-line prototype, not a finished hospital application. The chain provides a checkpoint publication audit trail. It does not run FedProx, aggregate models, verify local training, or establish privacy guarantees. Publisher permissions are controlled by one local coordinator. No IPFS, independent hospital services, web UI, external wallet or production deployment has been built. The prediction command and real model registration cannot run until training supplies a checkpoint. No placeholder checkpoint was manufactured. No contract security or end-to-end tests were executed.

## Training is the next dependent step

No training was started under the instruction to finish work before training. Choose the run budget before launching it in the visible VS Code integrated terminal. The current trainer defaults are 20 rounds, 3 local epochs, seed 42 and provisional mu 0.01; these are prototype choices, not evidence of optimality. Earlier smoke timings suggest hours, and the changed client profiles make the estimate approximate. Do not start the retired comparison workflow.

After a completed run: prepare its registration, publish hashes, verify them, then use `predict.py` with its best checkpoint. Commands are in the blockchain README. Reserve the completely new external dataset for the eventual final evaluation and do not use its performance to tune the prototype.

## Local node operations

The Hardhat node runs in the background on http://127.0.0.1:8545. Logs are `blockchain/chain.stdout.log` and `chain.stderr.log`. Its PID is in `blockchain/chain-process.json`. The node must remain running for registry commands. Hardhat state is in memory: after a node or machine restart, run `blockchain/start_chain.ps1`, then `registry.py deploy` to archive stale instance metadata and redeploy, then `registry.py status`. Previous model registrations must be republished on the new instance. Keep original receipts as history. The start script refuses a port already in use. Local unlocked deterministic accounts are for this development chain only. Old Ganache chain-data and deployment evidence are preserved but inactive.

## Training authorization update
The user has now authorized training. run_training.ps1 launches the documented prototype settings visibly in VS Code and registers the selected checkpoint after successful completion. Earlier statements that training was not authorized describe the previous stop point; current execution status is in fedprox_outputs/run_*/execution.json and RUN_LOG.md. External final evaluation remains deferred.

## Integration handoff update

API integration checks passed, including synthetic image uploads, selected global versions, accepted/rejected audits and simulated unavailable services. Actual chain receipt checks passed. Startup command reuses existing services and refuses replacement blockchain. Added RESULTS.md, OPERATIONS.md, DEMO_GUIDE.md and current dependency freeze. Browser/mobile visual checks remain unverified because inventory was empty. Independent evaluation remains invalidated by content overlap; prior results preserved with warnings. No new training performed.

## Local onboarding implementation

Added Hospital Management portal, SQLite organization registry, expiring signed wallet login/session, local administrator token, manual approval/rejection/suspension, separate on-chain membership directory, client signing/heartbeat CLI, and future enrolled-run path for exactly three approved ready local clients. Original completed FL run unchanged. Syntax/compilation passed; onboarding lifecycle and future enrolled training remain unverified. See HOSPITAL_ONBOARDING.md. No production readiness claimed.

## Screenshot feature implementation

Added owner-confined data/manifests, patient mapping checks, separately authorized local client keys, frozen portal campaigns, opt-in/start-stop, phase progress/loss/metrics, peer-report IPFS CIDs, signed submissions, pause/resume/cancel/retry/timeouts, pre-aggregation inspection/approval, own feedback, metadata-only exports and new global-version inference. Existing numerical primitives and completed study unchanged. Workflow/HTTP/live-local-services fixture checks passed; no actual hospital training launched and visual browser/mobile checks remain blocked. See PORTAL_WORKFLOW_GUIDE.md.

## Smoke-run leakage review,22 October2026
Completed portal campaign preserved. One probable transformed train/val image pair was found despite disjoint filename IDs. Reviewed data copy: database/hospitals_reviewed_v2. Existing registered data/results were not overwritten; new data registration and campaign are required. Review: D:\dataset\multiseed_outputs\campaign_leakage_review\20261022T080906_451339Z\REPORT.md. No longer training launched.
