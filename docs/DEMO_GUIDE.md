# Presentation guide

This curated folder is intended for a source walkthrough. It does not include
the dataset, trained checkpoints, local registrations, or generated run state
needed for a live demo.

## Suggested walkthrough

1. **Problem and scope** — introduce the goal: train a shared pneumonia
   classifier without centralizing each simulated hospital's training images.
   Be clear that the hospitals run on one computer.
2. **Architecture** — use [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)
   to trace the path from the incoming global model, through local training and
   peer review, to aggregation and publication of the next global model.
3. **Portal and coordination** — show `project_dashboard.py`,
   `hospital_management.py`, and `portal_workflow.py` as the access, enrollment,
   and campaign layers. `round_coordinator.py` is the visible orchestration
   entry point for registered rounds.
4. **Learning and acceptance** — explain that `fedprox_core.py` performs local
   learning, `hospital_workers.py` and `portal_workers.py` run local work, and
   `peer_policy.py` defines review decisions and aggregation weights.
5. **Storage and audit** — `architecture_io.py` handles local IPFS references
   and integrity checks. `blockchain/contracts/` and the Python adapters record
   membership, client authorization, updates, peer decisions, and global-model
   references. The chain does not prove that the reported training or reviews
   are honest.
6. **Results and limitations** — use [RESULTS.md](../RESULTS.md), emphasizing
   that the reported metrics are validation results from a historical run, not
   independent clinical accuracy.

## Likely questions

**Are the hospitals independent systems?** No. They are simulated on one
computer in this prototype.

**Are images written to the blockchain?** No. The chain records identifiers,
hashes, and decisions; model artifacts are handled off-chain.

**Does IPFS provide privacy?** No. Local artifact storage is not a formal
privacy mechanism, and model updates can still reveal information.

**Does the blockchain prove a model is correct?** No. It preserves recorded
claims and references; it does not prove the correctness of training, labels,
or peer validation.

**Is the reported score independently validated?** No. The historical results
are validation metrics and have documented dataset limitations. Do not present
them as independent test accuracy or clinical performance.

**Can I launch the full demo from this folder?** No. Required runtime state,
data, trained models, and setup launchers are not included.
