# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Hospital and administrator workflow

This guide supersedes the earlier local-client limitations in HOSPITAL_ONBOARDING.md. It describes the separate local campaign workflow; completed experimental artifacts and RESULTS.md remain unchanged.

## Hospital side

1. Open http://127.0.0.1:8765/hospital. Click **Connect browser wallet** to connect MetaMask and preload the login challenge. Then click **Sign in browser wallet** and approve the message. The portal verifies the signature and signs you in automatically; no signature paste or second sign-in click is needed. Submit an application if unregistered. The local training workspace, readiness controls and their navigation entries appear only after administrator approval. No owner private key is exported.
2. In **Local data & training workspace**, click **Prepare local client**. Review the authorization message, click **Sign client authorization**, and approve in MetaMask. The signature is submitted automatically and authorization is recorded without a separate confirmation button or signature field. This creates a separate development key and records its delegation in a separate local contract after verifying the owner's signature.
3. The panel shows the hospital's own assigned folder under local_operations/hospital_data/HOSPITAL_CODE. Copy images into train/NORMAL, train/PNEUMONIA, val/NORMAL and val/PNEUMONIA. Keep originals unchanged; use COPY for any new split. No final test images belong in local training/validation.
4. For filenames without reliable patient IDs, place patients.csv in that folder with columns `relative_path,patient_id`. Example relative path: `train/NORMAL/image.png`. Every unparsed image needs a mapped patient ID. IDs must identify real patients, not filenames masquerading as patient IDs.
5. Supply a documented **patient-ID namespace**. Use the same namespace for IDs from the same source across hospitals. Different namespaces do not prove different patients. Click **Check & register local data**. The check refuses exact-byte duplicates, within-source mapped patient overlap and train/val patient overlap. It does not establish perceptual/source independence automatically. Images are not deleted, relabeled or resplit.
6. Ask the administrator to register a campaign including this hospital. In **My campaigns**, click **Start local participation** to opt in. This does not secretly launch a process. **Stop local participation** withdraws at the next cooperative checkpoint and prevents further work; already committed updates remain immutable.
7. Watch own round/epoch/batch/loss, duration, local validation, generated model CID, signed submission receipt, peer results, acceptance/rejection and reasons. Local batch history and attempt errors stay under the owner's agent folder; use **Load my local log** for own details. The panel displays last successful global synchronization and approved configuration. Earlier and later round metrics can be compared in the own-round table.
8. Review administrator feedback. A rejected on-chain update cannot be overwritten. New updates are permitted in later registered rounds; failed uncommitted attempts can retry from the same incoming model with the same parameters. Changing data or an immutable submission requires a new registered campaign.

## Patient map example

```csv
relative_path,patient_id
train/NORMAL/image_a.png,PATIENT_A
train/PNEUMONIA/image_b.png,PATIENT_B
val/NORMAL/image_c.png,PATIENT_C
val/PNEUMONIA/image_d.png,PATIENT_D
```

Those are schematic IDs only. Do not invent IDs for real data. Supply both classes in each split. Local data folders are confined to the owning hospital, including junction/symlink checks.

## Administrator side

1. Open http://127.0.0.1:8765/admin and sign in using local_operations/admin.key. Review applications in Hospital Management. Only needed organization/contact-free coordination metadata is exposed; raw-image previews and private manifests are unavailable to admin APIs.
2. Open **Round operations**. Refresh network/campaigns to see IPFS/blockchain connectivity, all registered hospital states, recent heartbeats, delegate/data readiness and client submissions. Historical monitoring remains available separately.
3. Select exactly three approved clients with local configurations and signed delegation. Select the approved configuration (currently FedProx, local epochs 3, mu 0.01, seed 42). Register the total number of rounds before execution. Arbitrary unapproved hyperparameter changes are rejected. No test-based selection or revived FedAvg comparison is introduced.
4. All selected hospitals must opt in. Click **Start / get terminal command**. It returns a command like:

```powershell
.\.venv_runtime\Scripts\python.exe -u round_coordinator.py --campaign CAMPAIGN_UUID
```

Launch it in the visible VS Code terminal. Dashboard controls never create hidden training. Runtime on NEW hospital data is unmeasured; the earlier run's timing is not a guarantee. No real hospital campaign has been trained during implementation.

5. The coordinator holds the existing training lock, validates the frozen registration and data hashes, opens a new on-chain run with delegated signer membership and uses the original pretrained global version as its registered initialization. It never changes historical membership. Local development gas is funded only on the verified Hardhat chain.
6. Three local workers train using the existing FedProx primitive, upload model states to isolated IPFS, submit signed CIDs, and evaluate peers on their own validation images. Both other hospitals must approve under the existing balanced-accuracy rule. Reports are uploaded to IPFS and committed by hash. The administrator receives counts/metrics and model/report references; raw images are not returned.
7. The round pauses at **aggregation_ready**. Review eligible updates, weights and reports, then click **Approve aggregation**. Approval changes execution timing, not the documented acceptance rule or weights. Do not cherry-pick accepted updates. All rejected retains the previous global bytes. The new global model CID is committed and published to named IPFS Files.
8. Workers evaluate the global model locally. Only labels/scores without filenames or patient IDs reach coordination to calculate pooled validation metrics; these arrays are not exposed in admin APIs. Model selection remains validation balanced accuracy with first-round ties. New campaign globals become available for version-selected inference to admins and enrolled approved hospitals.
9. Use Pause/Resume/Cancel, or Retry failed steps after resolving errors. Pause is between steps; cancel/stop is cooperative and waits for active workers/IO to stop. Per-step timeout is registered. Retries reuse successful immutable uploads/commitments and recover missing local transaction receipts from live events. No second coordinator can train concurrently. Cancelled/completed campaigns cannot restart; failed attempts and logs are preserved.
10. Send coordination feedback to a selected enrolled hospital and export the auditable JSON history. Exports contain no private keys, patient manifests, raw images or image paths. The dashboard keeps unmeasured communication overhead and unavailable FedAvg comparison explicitly marked. Artifact bytes are NOT network overhead.

## Privacy and deployment boundary

This is a **single-laptop prototype**, with role-level API isolation and hospital-scoped worker folders, not operating-system isolation between real institutions. The operator of the machine can access its filesystem. All raw images remain in owner-local folders; they are not uploaded to IPFS/blockchain or shared in admin exports. Model weights can still leak information; no formal privacy or clinical guarantee is made. New prediction uploads remain in memory. Keep all keys private and the server loopback-only.

## Verification evidence

- multiseed_outputs/portal_workflow_checks.json: isolated coordination checks including privacy scopes, opt-in, retries, pause/resume/cancel, timeout, gate and policy decisions.
- multiseed_outputs/portal_http_checks.json: actual HTTP handlers with isolated organizations, signed login/delegation, access denials, prediction access and session revocation.
- multiseed_outputs/portal_live_checks.json: real local IPFS and signed blockchain round using synthetic update/validation fixtures and separate test directories/contracts. This is software integration evidence, NOT a model training result.
- multiseed_outputs/portal_dom_checks.json: static/generated DOM IDs and JavaScript syntax checks.

Failed test attempts are retained in the corresponding *_test_attempts folders. Test model references are placed under IPFS project-demos/portal_fixture_*, not real hospital training folders. No new training on actual hospital images was launched. A visible-terminal round using three configured hospitals remains the final real-data exercise. Browser automation inventory was empty; interactive visual/mobile layout verification remains unperformed.

Fresh dashboard update: the admin landing page now summarizes registered hospitals and the selected new campaign. The earlier experiment is collapsed under History. Both prediction portals exclude historical checkpoints by default and provide an explicit opt-in; no new campaign model means prediction is unavailable until a model is published. Historical artifacts are retained.

## Current non-IID staging data (21 October 2026)

Source: database/train. Seed42; approximately50/30/20 hospital sizes with label-skewed patient-group assignments. These staging copies are not yet dashboard-registered training/validation folders.

| Folder | NORMAL | PNEUMONIA | Pneumonia share |
|---|---:|---:|---:|
| database/hospital1 | 2372 | 1017 | 30.01% |
| database/hospital2 | 712 | 1322 | 65.00% |
| database/hospital3 | 314 | 1042 | 76.84% |

Old balanced copies: D:\dataset\archive\hospital_distributions\balanced_20261021T180150_211863Z. Exact image and inferred patient overlap between new hospitals is zero. Further patient-wise train/val splits are required before portal training. The original val/test have pre-existing patient overlap with the source train pool, so they are not independent final holdouts for these copies. Evidence: multiseed_outputs/hospital_distribution_latest.json.

## Hospital staging train/validation layout (22 October 2026)

Each database/hospital1, hospital2 and hospital3 now contains train/NORMAL, train/PNEUMONIA, val/NORMAL and val/PNEUMONIA plus an updated patients.csv. The split uses seed42 and approximately80/20 per class by whole inferred patients; non-IID hospital proportions are retained. All copied hashes verified. Old flat class folders are archived at D:\dataset\archive\hospital_distributions\flat_noniid_20261022T071620_861999Z. Copy the matching hospital train/,val/ and patients.csv into its dashboard-assigned hospital-code folder before registering local data. No training started. Evidence: multiseed_outputs/hospital_train_val_latest.json.

## Hospital code workspace update (26 October 2026)

New local client preparation creates `local_operations/hospital_data/<HOSPITAL_CODE>/train/{NORMAL,PNEUMONIA}` and `val/{NORMAL,PNEUMONIA}`. Existing UUID folders are preserved for historical manifest paths. Their contents are copied once into a code-named workspace when prepared; nothing is deleted or overwritten. Existing registered manifests are unchanged. If the portal shows the previous-folder notice, register the code-named workspace before creating a future campaign. Empty preserved folders produce empty new workspaces; copy your hospital data before registration. Code-named workspaces SNRSE, ASTER and RGRI were created during this update.
