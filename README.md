# Fed-Ledger

Fed-Ledger is a local research prototype for federated pneumonia-image
classification. It combines ResNet-18/FedProx client training, peer review,
off-chain model aggregation, local IPFS artifact storage, and a local Ethereum
audit trail.

The hospitals in this prototype are simulated on one computer. Blockchain
records model references and decisions; it does not train or aggregate model
weights. This project makes no claim of clinical validity or formal privacy
guarantees.

## Presentation references

- [Architecture diagram](docs/ARCHITECTURE_DIAGRAM.md)
- [Presentation guide and likely questions](docs/DEMO_GUIDE.md)
- [Hospital and administrator workflow](docs/PORTAL_WORKFLOW_GUIDE.md)
- [Historical results and limitations](RESULTS.md)

## Main source map

| Area | Files |
|---|---|
| Dashboard and portals | `project_dashboard.py`, `admin_dashboard.html`, `hospital_dashboard.html`, `portal_admin.js`, `portal_hospital.js` |
| Hospital access and campaign workflow | `hospital_management.py`, `portal_workflow.py`, `round_coordinator.py` |
| Local training and peer decisions | `fedprox_core.py`, `hospital_workers.py`, `portal_workers.py`, `peer_policy.py` |
| Model data, integrity, and dashboard views | `architecture_io.py`, `dashboard_data.py`, `predict.py`, `current_chain_explorer.py` |
| Local blockchain and contracts | `blockchain/protocol_chain.py`, `blockchain/hospital_directory.py`, `blockchain/client_authorization.py`, `blockchain/contracts/` |
| IPFS setup | `ipfs/setup_ipfs.py` |

## Scope of this folder

This is a presentation-focused source selection, not a complete installation.
It omits test scripts, historical report material, setup launchers, datasets,
trained checkpoints, registrations, and generated runtime state. A live demo
cannot be reconstructed from this folder alone. `requirements.txt` lists the
Python dependencies, but machine-specific Python, Node, and IPFS setup is not
included.

`RESULTS.md` describes a historical run; its datasets, model files, and
verification artifacts are not included here. Treat its reported validation
metrics and limitations exactly as documented.
