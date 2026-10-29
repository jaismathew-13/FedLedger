# Hospital and administrator workflow

This is a conceptual walkthrough of the local prototype, not an operating
manual. The presentation-focused folder omits runtime setup, local credentials,
datasets, and campaign artifacts.

## One round

1. **Hospital access** — `hospital_management.py` provides local organization
   records and signed wallet sessions. `portal_workflow.py` scopes portal
   operations to the hospital and records client authorization and campaign
   configuration.
2. **Campaign registration** — the administrator selects three approved
   simulated clients and freezes the training configuration and data
   manifests. Training is launched from a visible terminal by
   `round_coordinator.py`, not secretly from a dashboard request.
3. **Local training** — the coordinator distributes the current global model.
   Each client trains locally using the FedProx implementation in
   `fedprox_core.py`, with client work handled by `portal_workers.py` and
   `hospital_workers.py`.
4. **Artifact submission** — client checkpoints are stored through the local
   IPFS API. Their content identifiers and hashes are submitted to the local
   protocol contract through `blockchain/protocol_chain.py`.
5. **Peer review** — each candidate is checked by the other two clients on
   their own validation data. The policy in `peer_policy.py` requires both
   reviewers to approve; a candidate must score above 0.5 balanced accuracy
   and be no worse than the incoming model on the reviewer's validation set.
6. **Aggregation** — the administrator reviews eligible updates before
   aggregation. Accepted updates are weighted by training sample count and
   mean peer balanced accuracy. Rejected updates receive no weight; if all are
   rejected, the incoming global model is retained.
7. **Selection and audit** — the resulting global model is evaluated on
   validation data, and the best version is selected by pooled validation
   balanced accuracy. The contract records model references and decisions;
   it does not prove that training or review claims are correct.

## Main implementation files

- `project_dashboard.py` serves the local admin and hospital portals.
- `hospital_management.py` manages local organizations and wallet sessions.
- `portal_workflow.py` owns role-scoped data and campaign operations.
- `round_coordinator.py` orchestrates registered rounds.
- `fedprox_core.py`, `hospital_workers.py`, and `portal_workers.py` implement
  local model work.
- `peer_policy.py` implements peer acceptance and aggregation weights.
- `architecture_io.py` handles IPFS transport and file integrity.
- `blockchain/contracts/` and `blockchain/*.py` implement local audit records.

## Boundaries to explain

- This is a single-computer simulation, not deployment across independent
  hospitals.
- Raw training images are not submitted to the blockchain. Local model
  updates can still reveal information; no formal privacy guarantee is made.
- The blockchain preserves recorded commitments, not proof of correct
  training, labels, or peer reviews.
- Validation metrics are not independent test accuracy and do not establish
  clinical performance.
