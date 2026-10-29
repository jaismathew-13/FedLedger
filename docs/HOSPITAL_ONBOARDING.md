# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

> **Updated workflow:** See [PORTAL_WORKFLOW_GUIDE.md](PORTAL_WORKFLOW_GUIDE.md). Hospital-owned folders, MetaMask-authorized delegated clients and portal campaign controls are now implemented. The older roster/shared-data limitations below describe the earlier implementation and must not be used for new portal campaigns.

# Local multi-hospital prototype

## Scope

The completed experiment and its model files remain unchanged. Hospital Management is a separate local onboarding service backed by SQLite and a separately deployed HospitalDirectory contract on the same Hardhat chain. Approval is an organization/wallet membership attestation, not proof of legal identity or clinical suitability. An administrator must perform that review manually.

The project remains a single-laptop simulation. Hospital workers share this machine/GPU and use the configured patient-split dataset partitions. This is not a deployed network of actual hospitals. No clinical validity, formal privacy, Byzantine resilience or production security claim is made.

## Workflow

1. Refresh http://127.0.0.1:8765 and open **Hospital Management**.
2. A hospital connects a browser wallet or creates a local development wallet using hospital_client.py. It signs a one-use expiring login message. Private keys are not sent over HTTP.
3. Submit organization name/code. Status starts pending; registration does not enroll the wallet in an existing training run.
4. The local administrator enters the token from local_operations/admin.key into the portal. Never share that file or a hospital wallet.key. Tokens remain in browser memory; use Clear credentials when finished.
5. Review organization identity off-platform, provide a reason and approve/reject. Approval commits wallet authorization plus an opaque organization hash to the separate directory. Suspension revokes authorization for future rounds; rejection is local when the wallet was never authorized. Chain receipts and local review events are shown. The administration view checks chain/database reconciliation.
6. Approved clients send readiness/heartbeat. Online status is recent contact, not proof that training succeeded. Patient/label/local-data/client-readiness declarations are self-reported. No raw images or patient IDs are transmitted by this heartbeat.
7. Choose exactly three ready, approved, online hospitals and save a future enrollment snapshot. The three-client limit preserves the existing peer rule; arbitrary-size training is not implemented.
8. Launch a new run only when training is separately authorized. It produces a new output directory/run ID, signed hospital submissions, and an immutable run membership snapshot. Completed runs keep their historical members.

## Local client commands

Run in D:\dataset (substitute your organization code/name):

```powershell
.\.venv_runtime\Scripts\python.exe hospital_client.py create-wallet --code HOSPITAL_NORTH
.\.venv_runtime\Scripts\python.exe hospital_client.py apply --code HOSPITAL_NORTH --name "North Hospital"
.\.venv_runtime\Scripts\python.exe hospital_client.py status --code HOSPITAL_NORTH
```

After administrator approval, and only after performing the indicated checks:

```powershell
.\.venv_runtime\Scripts\python.exe hospital_client.py heartbeat --code HOSPITAL_NORTH --sample-count ACTUAL_LOCAL_COUNT --readiness-attested --watch
```

Replace ACTUAL_LOCAL_COUNT with an integer. Repeat for the other two hospitals in separate terminals. Client readiness does not start model training. The watch command sends contact every 30 seconds; online eligibility expires after 120 seconds and wallet sessions after 8 hours. Rerun the client after session expiry.

## Future local training

After an administrator saves the roster, its JSON is stored under local_operations/rosters. Start only after reviewing the expected runtime and authorizing a new experiment:

```powershell
.\.venv_runtime\Scripts\python.exe -u train_architecture.py --roster-file local_operations/rosters/ROSTER_ID.json
```

Use the visible VS Code terminal. To establish wiring first, add --smoke for a separate one-round run. No smoke or new run was launched during this implementation. Future-run membership/signing is not runtime-validated yet.

The existing FedProx, validation selection, peer thresholds, data partition scheme and aggregation calculations are retained. Identity labels/signers are taken from enrollment; actual local sample counts still come from the training partitions. The local coordinator can read development client key files because all clients run on one machine; that is a simulation boundary, not real-hospital key custody. External browser wallets can register but cannot execute local roster training without local client key files.

Gas funding for enrolled local wallets occurs only when a new roster training run is launched against the verified Hardhat chain. These are development funds only. Enrollment status/readiness is checked at each round boundary. A suspended/offline/not-ready client causes the future run to stop with preserved artifacts; it does not silently change the participant set or scientific protocol. Do not suspend clients mid-demo unless demonstrating that abort behavior. Membership suspension is not retroactive removal of historical transactions.

## Deployment and files

- Local administrator credential: local_operations/admin.key (generated at startup, ignored by Git).
- Operations database: local_operations/organizations.sqlite3.
- Local development hospital keys: local_operations/clients/CODE/wallet.key.
- Directory deployment: blockchain/deployment.directory.local.json; no original FL contract replaced.
- Compile directory only: `.\.tools\node-v22.23.3-win-x64\node.exe blockchain/compile_directory.cjs`.
- Status: `.\.venv_runtime\Scripts\python.exe -m blockchain.hospital_directory status`.
- Start interface safely: `.\.venv_runtime\Scripts\python.exe start_project.py`.

## Remaining boundaries

Loopback HTTP only; do not expose this built-in server publicly. Real deployment would need authenticated hospital transport, TLS, independently held signing keys, organization verification/identity provider, secret storage, rate limiting, durable chain operations, protected data governance and independently reviewed threat controls. The hospital registry is locally persisted, not a tamper-proof database; on-chain commitments cover membership state, not all administrative reasons. No patient images or identifiable predictions are committed to blockchain.

Python and JavaScript syntax checks and compilation passed. Wallet onboarding, approval/suspension and new enrolled training have not been exercised end to end. Existing completed-run integrity is separate. Do not call the new workflow validated or production-ready until those checks are performed.
