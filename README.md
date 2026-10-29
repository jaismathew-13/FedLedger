# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## FedLedger ? Project overview

A local hospital federation prototype using ResNet-18/FedProx, peer validation,
IPFS model storage and Ethereum/Solidity audit records.

This repository contains source code and documentation. Datasets, trained model
weights, private keys, hospital registrations, local deployments, runtime logs and
generated experiment evidence are intentionally kept outside version control.
Startup commands that reference an existing run require its locally generated model
and run artifacts; cloning this source repository alone does not supply them.
See [Startup](docs/STARTUP.md) and [Hospital workflow](docs/PORTAL_WORKFLOW_GUIDE.md).

Research prototype; no clinical validity or formal privacy guarantee is claimed.

Project navigation: [Full context](PROJECT_CONTEXT.md) | [Guides and folder layout](docs/README.md) | [Current hospital workflow](docs/PORTAL_WORKFLOW_GUIDE.md)

## Federated pneumonia prototype: FedProx

## Flowchart architecture

IPFS Desktop connects to the same isolated private project storage/API used by Python. See `ipfs/DESKTOP_SETUP.md`. Start the project IPFS service before Desktop; do not launch a competing daemon. Strict offline mode was replaced because it breaks Desktop's connectivity RPC.

The new full-protocol entry point is `train_architecture.py`: three parallel hospital processes, per-hospital checkpoints, isolated local IPFS, signed peer reviews, accepted-update aggregation, on-chain global CIDs and redistribution. See `docs/ARCHITECTURE_GUIDE.md` for setup, commands and limitations. The implementation is added; no full-architecture training has run. The sections below describe the preserved earlier prototype and its single-run entry point.

## Local prediction

After training creates a `best_model.pt`, run this in the VS Code terminal, replacing the example paths with real files:

```powershell
& 'D:\dataset\.venv_runtime\Scripts\python.exe' 'D:\dataset\predict.py' --checkpoint 'D:\dataset\fedprox_outputs\YOUR_RUN\best_model.pt' --image 'D:\path\to\xray.png'
```

Prediction uses the checkpoint's preprocessing and class mapping, and the same argmax decision rule as training evaluation. CPU is the default; add `--device cuda` to use the GPU. It prints JSON without copying or uploading the image. The input must be a chest X-ray; no image-type detector is implemented. Scores are model outputs, not calibrated clinical probabilities. Only load checkpoints you trust. No trained checkpoint is supplied by this command.

The active training workflow uses ImageNet-initialized ResNet-18, Adam with weighted cross-entropy plus the FedProx penalty at each simulated client, and sample-count-weighted off-chain aggregation. There is one method and one run per command; no baseline comparison, scenario sweep, mu grid search, paired comparison, or staged comparison runner remains active.

`train_fedprox.py` is the training entry point. `fedprox_core.py` contains the existing numerical routines. Defaults are 20 rounds, 3 local epochs, seed 42, workers 0, the former base client profiles, and provisional mu=0.01. These are prototype defaults, not evidence of optimality. The mu is configurable explicitly; no test result selects it.

Run from the VS Code integrated terminal, after deciding the training budget:

```powershell
& 'D:\dataset\.venv_runtime\Scripts\python.exe' -u 'D:\dataset\train_fedprox.py' --dataset-root 'D:\dataset_patientsplit' --rounds 20 --local-epochs 3 --mu 0.01 --seed 42
```

The command is an example, not an automatically started run. Training can take hours; choose the budget before launching. CUDA is required. The current patient split still has a small test set; the proposed larger holdout has not been created. Reserve and verify the final holdout before collecting final research results.

Each invocation writes a separate `fedprox_outputs/run_*/` folder containing configuration, client counts, terminal log, round history, and `best_model.pt` / `latest_model.pt`. Checkpoints are updated after each completed round. The best checkpoint uses validation balanced accuracy only, retaining the first round in a tie. Checkpoints contain inference weights and configuration, not full optimizer/RNG state for exact training resumption.

Test data is not loaded by default. Add `--evaluate-test` only when ready for final evaluation of the validation-selected checkpoint. Repeated test-driven changes invalidate the intended holdout evaluation.

Historical experiment results and interrupted-run logs remain in `multiseed_outputs/`. Retired comparison sources are preserved as non-executable text in `archive/comparison_workflow/`. They are historical evidence, not results from the new single-method trainer. The comparison monitor remains paused and must not restart the retired workflow.

The local Ethereum checkpoint audit registry is implemented under `blockchain/`; see its README and `docs/PROJECT_STATUS.md`. Training and aggregation remain off-chain. IPFS storage, peer validation, public-network wallet handling, a web interface and Docker deployment are not implemented. This is a prototype, without clinical approval or formal privacy guarantees.

Completed image-review helper sources are preserved in archive/completed_review_tools/ as text. Use .venv_runtime as the Python environment; obsolete broken environments and installation scratch were removed. Data-check and patient-split utilities remain available.

## Training and registration launcher
Run .\run_training.ps1 in the VS Code terminal for the authorized 20-round, 3-local-epoch, seed42, mu0.01 prototype run without test evaluation. It keeps Windows awake, refuses concurrent trainer processes, saves execution.json and round checkpoints, then prepares/registers/verifies the best checkpoint on the local Hardhat chain. Keep the laptop plugged in and lid open. The node must remain available for post-training registration. Failures preserve artifacts and are recorded in RUN_LOG.md.

## Final integration handoff

- [Operations and safe startup](OPERATIONS.md)
- [Results and rejection analysis](RESULTS.md)
- [Demo and presentation guide](docs/DEMO_GUIDE.md)
- [Dashboard feature coverage](docs/DASHBOARD_FEATURES.md)
- API check evidence: `multiseed_outputs/project_integration_checks.json`

Start the existing run: `.\.venv_runtime\Scripts\python.exe start_project.py`. No training is launched. Original Hardhat instance must remain running for live verification. Visual browser/mobile checks remain manual because browser control was unavailable.

## Local hospital onboarding

See [Hospital onboarding](docs/HOSPITAL_ONBOARDING.md) for wallet registration, administrator approval/suspension, client readiness and future three-client enrollment. The separate directory does not alter completed run membership. This is a single-laptop prototype, not a production hospital deployment. No new enrolled training has been exercised.

## Role-specific dashboards

- Hospital portal: http://127.0.0.1:8765/hospital (default root); wallet login and own hospital workspace.
- Administrator console: http://127.0.0.1:8765/admin; local administrator token required.

See [Dashboard roles](docs/DASHBOARD_ROLES.md) for access controls. Existing API integration evidence predates the role split and must not be treated as verification of the new ACL flows.

## Hospital/client and round operations

See [Portal workflow guide](docs/PORTAL_WORKFLOW_GUIDE.md) for own data setup, MetaMask-signed delegated clients, round management, safe controls, peer validation, IPFS and signed blockchain submission. Launch real training only in the visible VS Code terminal. No real hospital campaign was started while implementing this extension. Test evidence is under multiseed_outputs/portal_*checks.json and is explicitly labeled software fixtures.
