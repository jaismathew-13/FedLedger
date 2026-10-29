# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Project context

Updated 25 October 2026. Current consolidated project handoff. This describes a local research prototype, not a production hospital deployment. Earlier revisions are preserved under archive/document_history/.

## 1. Purpose

The project trains a pneumonia classifier through simulated federated learning. Hospitals train ResNet-18 on their own chest X-ray partitions, exchange model checkpoints through IPFS, evaluate one another's updates, and record commitments on a local Ethereum-compatible blockchain.

Classes: NORMAL and PNEUMONIA.

The current approach is **FedProx local training with a project-specific peer-validation gate and validation-aware aggregation**. The peer gate and aggregation extension should not be described as standard FedProx alone. No current FedAvg comparison result is established.

## 2. Components and responsibilities

| Component | Responsibility |
|---|---|
| ResNet-18 / PyTorch | Learns image features and predicts the two classes |
| FedProx | Adds a penalty that discourages a local model from drifting too far from the incoming global model |
| Hospital workers | Read their assigned images, train, evaluate peers, and evaluate global models |
| Coordinator | Schedules rounds, collects evidence, applies the registered decision/aggregation rules and publishes global versions |
| IPFS / Kubo | Stores checkpoint and report bytes and returns content identifiers |
| Hardhat / Solidity | Stores run membership, model references and validation commitments on a local development chain |
| Python HTTP server | Exposes authenticated application APIs and serves the dashboards |
| HTML/CSS/JavaScript | Implements separate admin and hospital interfaces; this is not Streamlit |
| SQLite | Stores applications, sessions, readiness, campaigns, participation and coordination events |
| Rich | Displays terminal training progress |

## 3. Identity and enrollment

The administrator signs in with the local administrator token. Hospitals sign a one-use login challenge using their wallet, such as MetaMask. The server recovers the signing address and issues a temporary session. Logging out revokes it.

A hospital application begins pending. An administrator reviews it and supplies a reason:

- Pending can become approved or rejected.
- Approved can become suspended.
- Suspended can become approved again.
- A rejected application has no direct status transition in the current interface.

Approval and suspension update the local HospitalDirectory contract. The dashboard compares local status with live contract membership. A wallet signature proves control of that wallet; it does not independently prove the applicant's real-world institutional identity.

Approved hospitals prepare a separate local training client. The application creates a development signing key in that hospital's agent folder. The owner reviews and signs a delegation message. The server verifies the signature before recording the delegation through ClientAuthorization. The owner's MetaMask private key is not exported.

Readiness heartbeats indicate recent reported availability. They are self-reported and expire; they are not a medical-data quality certification.

## 4. Hospital data setup

Each hospital has an assigned folder:

```text
local_operations/hospital_data/<HOSPITAL_CODE>/
  train/NORMAL/
  train/PNEUMONIA/
  val/NORMAL/
  val/PNEUMONIA/
  patients.csv
```

`patients.csv` maps `relative_path,patient_id` when filenames do not provide reliable patient IDs. The same patient's images must stay in one split. Training and validation both need both classes.

Registration checks file hashes, mapped patient overlap and folder boundaries. A documented patient-ID namespace lets IDs from the same source be compared across hospitals. Different namespaces do not prove different people. Byte-level duplicate checks do not rule out all cropped or re-encoded copies.

Private manifests record paths and hashes for later integrity checks. Admin APIs receive aggregate counts and configuration metadata, not raw-image paths or private manifests. Existing source images are never deleted or overwritten by these checks.

## 5. Registering a training campaign

The admin selects exactly three approved hospitals with configured data and signed client delegation. The approved configuration currently uses FedProx, three local epochs, mu 0.01 and seed 42. A new campaign registers its total round count before execution.

Registration freezes participants, data versions, source hashes and parameters. All hospitals opt in before execution. The admin's Start control returns a command:

```powershell
.\.venv_runtime\Scripts\python.exe -u round_coordinator.py --campaign CAMPAIGN_UUID
```

Training is launched in the visible VS Code terminal. The web button does not launch hidden training. A training lock prevents concurrent coordinators.

## 6. What happens in one round

1. The coordinator checks registration, data integrity, approvals, participation and the active chain.
2. Each hospital downloads the same incoming global checkpoint and verifies its hash.
3. Each hospital trains locally using its own training images.
4. The hospital saves a `.pt` checkpoint and uploads it to IPFS.
5. Its delegated client signs a blockchain submission linking the update CID, digest and round.
6. Both other hospitals evaluate that update using their own validation subsets. They also evaluate the incoming global model on those same subsets.
7. Peer results are collected; the documented gate decides acceptance.
8. The admin reviews eligible updates and approves aggregation execution.
9. The coordinator aggregates accepted models off-chain, or retains the previous global model if every update is rejected.
10. The new global checkpoint is stored in IPFS and its reference is committed on-chain.
11. Hospitals evaluate the global model locally. The coordinator computes pooled validation metrics and records the selected model.
12. The next round begins unless the campaign is complete, paused or cancelled.

Local training uses class-weighted cross-entropy and Adam. FedProx adds:

```text
local objective = classification loss + (mu / 2) * squared distance from incoming global parameters
```

There is no separate “local aggregation algorithm” inside a hospital: its optimizer updates one local model. Aggregation combines the resulting hospital models at the coordinator.

## 7. Acceptance and aggregation

Both other hospitals must approve an update. On each reviewer's own validation data, the candidate must:

- Have balanced accuracy strictly greater than 0.5.
- Have balanced accuracy at least as high as the incoming global model.

Missing, duplicate or invalid reviews reject the update. Model loading also checks tensor structure and finite values.

Balanced accuracy is the average of sensitivity and specificity.

For accepted update i:

```text
mass_i = training_sample_count_i * mean_peer_balanced_accuracy_i
weight_i = mass_i / sum(mass of all accepted updates)
new_global = sum(weight_i * local_model_i)
```

Rejected updates receive zero weight. If none are accepted, the incoming global model bytes are retained. Admin approval releases the aggregation step; it does not permit overriding acceptance or choosing favorable updates.

Rejected on-chain submissions cannot be edited. Later rounds can submit new updates. Failed uncommitted steps may retry under the registered configuration. Changing immutable submissions or registered data requires a new campaign.

## 8. Model selection and prediction

The best checkpoint is selected using pooled validation balanced accuracy. Ties keep the earlier selected round. The test set does not select rounds or parameters.

The prediction interface loads a selected, hash-checked model version, applies the evaluation preprocessing, runs ResNet-18 and displays NORMAL/PNEUMONIA scores. Scores are uncalibrated model outputs, not validated diagnostic probabilities.

Uploaded prediction images are handled in memory and are not written to the blockchain. The model does not reliably establish that every uploaded image is actually a chest X-ray.

## 9. Storage and audit

| Location | Contents |
|---|---|
| Hospital data folders | Raw training and validation images |
| Private manifest folders | Image paths, fingerprints and patient mapping references |
| Hospital agent folders | Local client key, checkpoints, progress and local logs |
| IPFS | Model checkpoints and new-campaign validation reports |
| Blockchain | Contract membership, run references, CIDs, digests and validation commitments |
| SQLite | Application and campaign coordination state |
| `architecture_outputs/` | Completed architecture experiment artifacts |
| `multiseed_outputs/` | Reported numerical evidence and software verification reports |
| `RUN_LOG.md` | Commands, changes, errors and operational history |

A CID identifies IPFS content. A SHA-256 digest lets the application compare expected and retrieved file bytes. A transaction hash identifies a blockchain transaction; a successful receipt confirms inclusion on that chain.

These checks can detect mismatched artifacts. They do not establish correct labels, truthful validators or useful medical predictions.

The IPFS Desktop Files view uses named references. Original run models appear under `/training/<run ID>`; new campaign models use `/training/portal_<campaign ID>`. Synthetic test artifacts use `/project-demos/` and must not be presented as real training outputs.

The historical experiment committed validation evidence hashes; newer portal campaigns additionally upload validation reports to IPFS.

## 10. Dashboards

Admin portal: http://127.0.0.1:8765/admin

- Reviews hospital applications and authorization.
- Shows hospital readiness, network connectivity and missing setup.
- Registers campaigns and controls pause/resume/cancel/retry.
- Reviews submissions, peer decisions and aggregation evidence.
- Releases the aggregation gate.
- Views validation history, model versions and recorded transactions.
- Sends hospital-specific coordination feedback and exports audit history.
- Performs research prediction and integrity checks where references are available.

Hospital portal: http://127.0.0.1:8765/hospital

- Signs in with its own wallet and views its application.
- Prepares and authorizes its own local client.
- Registers local data and reports readiness.
- Opts into or stops participation in enrolled campaigns.
- Views its own progress, loss, validation metrics, CIDs, receipts and rejection reasons.
- Reads its own logs and admin feedback.
- Uses permitted model versions for research prediction.

Pause happens at safe workflow boundaries. Local stop/cancel is cooperative and may wait for a batch or network operation. It cannot erase an already committed transaction.

## 11. Main code functions

| File / function | What it does |
|---|---|
| `hospital_management.py`: challenge, login, wallet, logout | Wallet authentication and session lifecycle |
| register, transition, heartbeat, me, list | Applications, status changes, readiness and role-scoped views |
| `portal_workflow.py`: prepare_agent, authorize_agent | Creates and delegates a local training signer |
| configure | Validates hospital data and saves its private manifest |
| create | Freezes a new campaign's participants, data and configuration |
| participate, control | Hospital opt-in and coordinator execution controls |
| overview, feedback, export, local_log, model | Role-scoped monitoring, audit and model access |
| `round_coordinator.py`: run_campaign | Runs the complete multi-hospital round state machine |
| `portal_workers.py`: train, review, evaluate | Local training, peer validation and global evaluation jobs |
| checkpoint / progress callbacks | Cooperative stop checks and progress reporting |
| `hospital_workers.py`: load_state | Validates model state structure and values |
| train_hospital, review_at_hospital | Core hospital training and peer evaluation operations |
| `fedprox_core.py`: build_model | Constructs ResNet-18 with the two-class output |
| client_update | Runs local Adam optimization with the FedProx penalty |
| evaluate, compute_metrics | Produces scores, confusion counts and classification metrics |
| sample_weighted_aggregate | Combines compatible model states using supplied weights |
| `peer_policy.py`: decide_update, aggregation_weights | Applies the frozen acceptance and weighting rules |
| `architecture_io.py`: LocalIPFS.add, fetch | Uploads artifacts and verifies retrieved artifact hashes |
| sha256, write_json, read_json | Integrity hashes and reliable local metadata IO |
| `blockchain/protocol_chain.py`: ProtocolChain | Opens runs, submits updates/reviews and publishes global references |
| `blockchain/hospital_directory.py`: Directory | Reads and updates hospital authorization |
| `blockchain/client_authorization.py`: ClientAuthorization | Records and checks delegated-client eligibility |
| `project_dashboard.py`: main / HTTP handlers | Serves pages and enforces API access |
| `dashboard_data.py` | Builds historical experiment, receipt and integrity views |
| `predict.py`: predict_image | Runs inference with a selected checkpoint |
| `start_project.py` | Checks the authorized chain, starts/reuses IPFS and serves/reuses the dashboard |

## 12. What has been completed

- Working admin and hospital dashboards with role-specific sidebar navigation, a top navbar and a responsive hamburger drawer.
- Wallet-signed hospital login, administrator approval, delegated client authorization, local data checks and campaign registration.
- Unequal hospital sizes and disease proportions, patient-grouped training/validation splits, copy manifests and content-hash verification.
- Local GPU training, peer evaluation, signed model submissions, approval-gated aggregation, IPFS publication and global evaluation.
- Audit views, hospital-scoped logs/feedback, model-version prediction and audit export.
- A completed original architecture experiment and a later completed dashboard-driven smoke campaign.
- Content duplicate audits, recoverable duplicate quarantine and a subsequent review of transformed-image leakage.
- A corrected staging dataset prepared for a new campaign; not yet registered or evaluated.
- Restart handling that preserves completed/cancelled campaigns as historical evidence and blocks automatic migration of unfinished campaigns.

## 13. Experiments: keep their results separate

### A. Earlier simulated-hospital architecture experiment

Run: `run_20261020T093433_860908Z`. ResNet-18, FedProx mu 0.01, seed 42, three local epochs and twenty rounds. Selected round: 11.

Selected validation accuracy: 98.7005%; balanced accuracy: 98.7005%; ROC-AUC: 0.998578. These are validation metrics, not independent test accuracy.

Peer gating rejected many updates and later rounds retained the previous global model. Retention must not be presented as evidence of continued learning or convergence. See [RESULTS.md](RESULTS.md) and saved evidence in `multiseed_outputs/architecture/run_20261020T093433_860908Z/`.

### B. Dashboard hospital smoke campaign

Campaign: `34c72e51-c98a-4a99-be9a-a540dce32a35`.

Participants: SNRSE, ASTER and RGRI. One federated round; three local epochs; seed 42; mu 0.01. All three hospital updates were accepted after both peer reviewers approved.

| Global validation metric | Saved result |
|---|---:|
| Accuracy | 98.3013% |
| Balanced accuracy | 98.3020% |
| Sensitivity | 98.5185% |
| Specificity | 98.0854% |
| Precision | 98.0826% |
| F1 | 0.983001 |
| ROC-AUC | 0.998970 |

Validation images: 1354. Confusion counts: TP665, FN10, FP13, TN666. Recorded round duration: 404.85 seconds.

The peer decisions, aggregation weights, aggregated model tensors, checkpoint hash and then-live blockchain receipts were independently checked. This establishes mechanical workflow consistency. It does not establish generalization or clinical validity.

A later review identified a probable transformed-image pair crossing this campaign's training/validation boundary. Its saved result remains preliminary smoke-test evidence. It must not be transferred to the corrected split or described as independent final accuracy.

Evidence: `multiseed_outputs/portal_campaigns/34c72e51-c98a-4a99-be9a-a540dce32a35/history.json`, `selection.json`, `status.json` and `result_verification.json`.

## 14. Data preparation and current versions

### Source duplicate cleanup

The inspected source was `D:\dataset\database`. Exact file hashes, decoded pixel hashes and perceptual similarity were compared. Confirmed duplicates outside protected `database/train`, `database/val` and `database/test` were moved to a recoverable quarantine. Protected source images were verified unchanged.

Moved image copies: 8507. Archive: `D:\dataset\archive\database_duplicate_quarantine\20261021T174752_077910Z`.

The original audit and cleanup manifests remain under `multiseed_outputs/database_duplicates/` and `multiseed_outputs/database_duplicate_cleanup/`. Perceptual similarity alone was not used for blanket deletion.

### Original non-IID staging folders used for smoke

`database/hospital1`, `database/hospital2` and `database/hospital3` were copied from unique contents in `database/train`, with approximate50/30/20 sizes and unequal disease proportions. Each has `train/NORMAL`, `train/PNEUMONIA`, `val/NORMAL`, `val/PNEUMONIA` and `patients.csv`.

| Staging folder / registered hospital | Train NORMAL | Train PNEUMONIA | Val NORMAL | Val PNEUMONIA |
|---|---:|---:|---:|---:|
| hospital1 / SNRSE | 1898 | 814 | 474 | 203 |
| hospital2 / ASTER | 570 | 1058 | 142 | 264 |
| hospital3 / RGRI | 251 | 834 | 63 | 208 |

The hospital-wide pneumonia shares are approximately 30%, 65% and 77%. Patients inferred from filenames were kept within a hospital and within one split. Source patient IDs were inferred, so this is not proof of true institutional or patient independence. Original source val/test also have pre-existing overlap with source train; do not treat them as independent holdouts for these copies.

### Transformed-image review and corrected v2

Review scanned 6779 image contents. It found 59 distinct-filename-patient perceptual candidate pairs, including 28 train/validation pairs. All candidate pairs were visually reviewed. One probable transformed radiograph pair was identified: SNRSE training `NORMAL2-IM-0095-0001_aug_581.jpg` versus validation `NORMAL2-IM-0096-0001_aug_249.jpg`.

A separate reviewed copy is prepared at:

```text
D:\dataset\database\hospitals_reviewed_v2\
  hospital1\train\NORMAL\
  hospital1\train\PNEUMONIA\
  hospital1\val\NORMAL\
  hospital1\val\PNEUMONIA\
  hospital1\patients.csv
  hospital2\...same structure...
  hospital3\...same structure...
```

The suspected image families are conservatively grouped in `patients.csv` and kept together in training. This is a reviewed image-family link, not confirmed real-world patient identity. No image is discarded or relabelled. The original registered dataset and completed campaign remain intact.

| Corrected staging folder | Train NORMAL | Train PNEUMONIA | Val NORMAL | Val PNEUMONIA |
|---|---:|---:|---:|---:|
| hospital1 | 1899 | 814 | 473 | 203 |
| hospital2 | 570 | 1058 | 142 | 264 |
| hospital3 | 251 | 834 | 63 | 208 |

**V2 is not yet registered or evaluated. No revised accuracy is available.** Exact duplicate and inferred-group checks passed, but perceptual screening can miss additional transformations. The reviewed copy is not certified independent.

Review evidence: `D:\dataset\multiseed_outputs\campaign_leakage_review\20261022T080906_451339Z/REPORT.md`. Current v2 summary: `multiseed_outputs/hospital_reviewed_v2_latest.json`.

## 15. Operational state at this handoff

On 25 October 2026, startup failed because the launcher rejected every campaign record. The smoke execution status was completed, while the database still held the earlier UI command `waiting_for_terminal`.

The launcher now checks saved execution status and round history. It allows completed/cancelled campaigns to be archived as historical records and refuses automatic replacement with unfinished campaigns. The completed campaign database status was synchronized to completed.

A new local chain was started and the dashboard/IPFS endpoints passed checks. After that chain replacement:

| Hospital | Application | Delegated client | Data registration |
|---|---|---|---|
| SNRSE | Pending reapproval | Requires new authorization | Existing smoke data retained |
| ASTER | Pending reapproval | Requires new authorization | Existing smoke data retained |
| RGRI | Pending reapproval | Requires new authorization | Existing smoke data retained |

This is a dated snapshot, not a guarantee that services remain running after another shutdown. Old transaction receipts cannot be verified against a newly created chain, even when chain ID and deployed addresses repeat.

Archive and checks: `multiseed_outputs/startup_repair_checks.json` and `local_operations/chain_archives/restart_20261025T155445_004093Z/`.

## 16. Starting the system

Open VS Code in `D:\dataset`, then open a PowerShell terminal.

After a reboot or a lost development chain:

```powershell
cd D:\dataset
.\.venv_runtime\Scripts\python.exe start_local_system.py --fresh-chain
```

If the matching chain remains running:

```powershell
.\.venv_runtime\Scripts\python.exe start_local_system.py
```

The launcher starts/reuses Hardhat and isolated IPFS, verifies deployments and starts/reuses the dashboard. Fresh-chain replacement archives the old references and marks hospital approvals/delegations for renewal. Unfinished campaigns require reviewed migration. It does not train a model.

| Service | Address |
|---|---|
| Admin portal | http://127.0.0.1:8765/admin |
| Hospital portal | http://127.0.0.1:8765/hospital |
| IPFS Web UI | http://127.0.0.1:5002/webui |
| IPFS Desktop API | http://127.0.0.1:5002 |
| MetaMask Hardhat RPC | http://127.0.0.1:8545 |

MetaMask network name: Fed-Ledger Local; chain ID 31337; symbol ETH. Add it through the extension's network settings. Hardhat must be running for chain-ID retrieval.

Keep the dashboard terminal open. Training is launched separately through the campaign command in a visible VS Code terminal.

## 17. Verification completed and its boundaries

- Isolated workflow checks cover registration/configuration, role scopes, opt-in, retries, timeouts, pause/resume/cancel, immutable completion and aggregation approval.
- HTTP handler checks cover authenticated routes, access denials, signature replay, data ownership, prediction and logout.
- Edge browser fixtures exercise both portals' buttons, sidebar links, hamburger drawer, registration, client authorization, campaign controls, export and prediction. Browser API responses and wallet signing are simulated in those checks.
- A real dashboard campaign subsequently exercised training, peer validation, IPFS and blockchain, with independently verified aggregation and receipt evidence.
- Startup migration checks cover completed-versus-running campaigns, archive integrity and live service connectivity.
- Software tests and synthetic fixtures are not model accuracy evaluations. Real MetaMask extension behavior is distinct from simulated browser signing. The dataset limitations above remain.

Evidence files include `multiseed_outputs/dashboard_button_verification.json`, `portal_http_checks.json`, `portal_workflow_checks.json`, `startup_campaign_migration_checks.json` and `startup_repair_checks.json`.

## 18. Remaining work, in order

1. Reapprove hospitals and reauthorize local clients after chain replacement.
2. Migrate the reviewed v2 data into a new registered data version while archiving existing registered input folders/manifests for historical reproducibility. Copy `patients.csv` together with the images. Avoid overlaying copies that leave the former validation image behind.
3. Register a new campaign with frozen participants, data, parameters and stopping plan. Do not resume a completed campaign using changed inputs.
4. Validate the corrected workflow, then run the agreed longer experiment and repeated seeds with a pre-registered configuration. The current approved portal configuration fixes seed 42; additional seeds need an explicit configuration extension first.
5. Obtain a genuinely independent patient-wise test dataset, audit it against all training/validation sources, and evaluate the selected frozen model.
6. Report uncertainty, limitations and unsuccessful/rejected updates honestly.

No longer campaign or revised-data evaluation has been launched.

## 19. Scientific and deployment boundaries

This is a single-laptop multi-hospital simulation. Application roles restrict APIs; the laptop operator can access local files. Raw images are not uploaded by this workflow, but model weights may reveal training information. No formal differential-privacy or secure-aggregation guarantee is implemented.

The blockchain records commitments and authorization; it does not prove correct labels, honest validation or useful medical predictions. Local isolated IPFS is not demonstrated multi-institution infrastructure. Hardhat is ephemeral development infrastructure.

Single-dataset experiments, limited seeds, inferred patient identity, augmented images and validation-guided weighting/selection limit performance claims. No claim of clinical validity, Byzantine robustness or novelty is established. A real deployment needs institutional identity checks, network/secret isolation, persistent services and independent security review.

## 20. Working rules and reference documents

- Preserve source datasets; re-splits and corrections use copied versions.
- Keep original completed run records and unfavorable/rejected outcomes.
- Select checkpoints using validation balanced accuracy only; never select using final test results.
- Record commands, edits, timestamps and errors in `RUN_LOG.md`.
- Launch new training in a visible VS Code terminal and avoid duplicate coordinators.
- Use saved evidence under `multiseed_outputs/` for reported experimental numbers.
- Never expose private keys or the administrator token in reports.

References: [Startup](docs/STARTUP.md), [Hospital/admin workflow](docs/PORTAL_WORKFLOW_GUIDE.md), [Operations](OPERATIONS.md), [Results](RESULTS.md), [Guides index](docs/README.md).

## Current-chain explorer (26 October 2026)

Admin sidebar > Blockchain explorer now displays live JSON-RPC blocks, starting with genesis where available. Includes contract deployments, hospital approval/suspension MembershipChanged events, DelegateAuthorized events and training-contract events. Refresh latest blocks, search by block number, filter hospital/client/training events and inspect transaction hashes, receipt status, timestamp, block/parent hashes and decoded event arguments. Paging is bounded to25 blocks by default with a server maximum100. Anonymous and hospital-user access to /api/current-blocks is denied. Historical saved experiment receipts remain under History and are not mixed with the current chain. No public Etherscan is required.

Examples on the verified current instance: RGRI approval block4, ASTER block8, SNRSE block10, BMH block11. These numbers belong to that instance; after a Hardhat reset, use the current-chain explorer rather than assuming old block numbers still apply.

## Independent blockchain demonstration
Use docs/BLOCKCHAIN_VERIFICATION.md for direct PowerShell JSON-RPC requests to the running Hardhat node, including live blocks and transaction receipts. These requests bypass the dashboard and saved files. This is verifiable local development-chain activity; public-chain/decentralization claims remain outside the demonstrated scope.

## Independent Blockscout explorer setup (26 October 2026)

Configuration and launcher: blockchain/blockscout/; guide: docs/BLOCKSCOUT.md. Official upstream compose checkout pinned at9cd48cc0708d520f093ec8a8c37d9a998b258171. Intended address http://localhost:4000, reads existing Hardhat31337 independently of dashboard. WSL3.0.3 installed; Windows reports reboot required. Docker Desktop installer download in progress. Explorer has not run or been verified. Raw current blocks0..12 and receipts archived in multiseed_outputs/blockscout/chain-before-install.json; evidence is not a restorable chain snapshot. No reset, training, or transactions performed.

Blockscout setup update: Docker Desktop per-user installation completed successfully; WSL3.0.3 installed. Docker Compose configuration validation succeeded. Engine/explorer are not running; required Windows restart and first-launch Docker terms review remain. Existing Hardhat instance unchanged. See multiseed_outputs/blockscout/setup_status.json. No claim of runtime success until live RPC/explorer hashes are checked.

## Hospital workspace and wallet sign-in update (26 October 2026)

Hospital data workspaces now use the registered organization code. Preparing a client creates train/val class folders under that code. Legacy UUID folders and frozen manifests are preserved; the portal flags a previous-folder registration so new workspace data can be registered for future campaigns. SNRSE, ASTER and RGRI code folders were created; the existing legacy folders were empty at migration time. Local workspace/readiness/participation and sidebar links are hidden until approval; the workspace API also requires local and live on-chain approval. MetaMask login now creates a fresh challenge, requests the signature and verifies it automatically; the signature input and manual verification button were removed. Account switching clears the hospital session. Blockchain/IPFS/training behavior is unchanged. No test suite or training was run for this update.

## Project name

The current project name is **Fed-Ledger**. Both portals, their page titles, the shared sidebar/logo, new wallet login/delegation messages and audit export filename use this name. Historical signed messages and the original on-chain organization commitment namespace remain unchanged for compatibility.

Client authorization now uses two controls: Prepare local client and Sign client authorization. After MetaMask approves the message, the portal automatically submits the signature to the existing owner-verification/on-chain authorization endpoint. No manual signature field or separate confirmation is shown. Controls are locked during requests to prevent duplicate submissions; account/session changes abort submission. Workspace status refreshes automatically.

## Code-folder registration correction

Renaming the displayed workspace does not update previously registered data manifests. Campaign71557a2c-c65f-4a6c-944c-df395e190920 failed before training because its frozen registrations still referenced UUID folders. This failed campaign and its manifests are preserved. Future campaign creation now rejects such registrations, and the admin labels affected hospitals re-register code folder. Each owner must click Check & register local data for the code-named workspace; then create a replacement campaign and opt in. No retrospective campaign rewrite or hash-check bypass is performed.

## Retired obsolete active data registrations

The current SNRSE/ASTER/RGRI code folders were byte-hashed and have no cross-hospital exact image overlap. Their data assignments differ from the original UUID registrations, which caused sequential registration to conflict with another hospital's stale manifest. After a SQLite/client-row backup and confirming no active training, only obsolete active manifest/summary pointers were cleared. Original manifests, campaign history, signed delegations and all image files were retained. Audit and retirement records are in multiseed_outputs/workspace_overlap_diagnosis.json and legacy_registration_retirement.json. Each hospital must register its code-named folder before a new campaign; exact-image and patient-overlap checks remain enforced. Zero byte overlap does not establish perceptual or patient independence.

## Wallet request sequencing

Connect browser wallet now connects and preloads the expiring login challenge. Sign in browser wallet requests personal_sign directly from the click, without a preceding network/account request. The client authorization button also signs its already-prepared message directly; account/session checks follow the signature and server verification remains enforced. This restores preloaded-message behavior without restoring the removed preview or signature fields. MetaMask/browser focus behavior still cannot be guaranteed; pending-request hints remain.

## Fresh-chain startup review (27 October 2026)

The startup path now initializes workflow tables for empty installations, archives failed campaigns without deleting their error/history, verifies complete round sequences and all contract dependencies, refuses foreign RPC services, and acquires the training/migration lock. An atomic migration journal and archive hash checks support recovery after partial deployment or database-reset failure. The healthy-chain check is repeated under the lock to avoid competing-startup replacement. Scientific training logic and datasets are unchanged. Fifteen isolated mocked startup checks passed; evidence is in multiseed_outputs/fresh_chain_startup_checks.json. A read-only live probe found the local chain unavailable, so no real reset/deployment was attempted. Readiness findings are in multiseed_outputs/fresh_chain_live_preflight.json.

## Blockscout explorer operational (27 October 2026)

Docker engine and WSL2 are now running. Local services were started using the archived fresh-chain workflow; all original campaign JSON, model/data files and previous chain evidence remain preserved. Hospital approvals/delegations require renewal on this new instance. Blockscout now serves http://localhost:4000 independently of the project dashboard. Its homepage, Blocks page and block/transaction API were checked; all indexed blocks and deployment receipts matched direct Hardhat RPC. Exact image digests and comparisons are recorded in multiseed_outputs/blockscout/live_verification.json. No training was launched. Later chain resets require stopping the old explorer/index first and following docs/BLOCKSCOUT.md so historical indexes are not silently reused.

## Administrator authentication controls

The duplicate Administrator review token field and Load administration view/Clear credentials controls were removed from Hospital Management. The existing sign-in page now retains its token in a JavaScript memory variable, and hospital administration loads automatically after successful login. An admin-only Logout button appears in the top navbar after login; it clears the in-memory token and returns to sign-in. Decision feedback remains next to Record decision and is hidden until used. No authentication checks were removed or credentials persisted in browser storage.

Hospital approval/rejection/suspension no longer requires a typed review reason. The admin reason field was removed; the server accepts an omitted reason while retaining administrator authorization, status-transition checks and decision/transaction audit records. Optional reasons from other clients remain limited to500characters.

## Project title and dashboard name ? 28 October 2026

The dashboard product name is **FedLedger**. Use **Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain** as the formal title for documentation and newly created reports. Shared display labels are defined in `project_identity.py`; they do not replace signed-message domains or immutable protocol identifiers. Historical evidence files remain unchanged.
