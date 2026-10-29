# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Fed-Ledger architecture

This diagram describes the implemented local multi-hospital prototype. Three hospital workers run on this laptop; it is not yet a deployment across independent hospital systems. The current registered-campaign entry point is `round_coordinator.py`.

```mermaid
flowchart TB
    subgraph CONTROL["Access and coordination"]
        HP["Hospital portal + MetaMask<br/>Register, sign in, authorize local client"]
        AP["Admin portal<br/>Approve hospitals, select three participants<br/>Register campaign and approve aggregation"]
        CO["Round coordinator<br/>Frozen participants, data versions and FedProx configuration<br/>Started in visible VS Code terminal"]
        HP -->|"Approved membership and signed delegation"| AP
        AP --> CO
    end

    G["Incoming global ResNet-18<br/>Initial model: ImageNet weights + two-class head<br/>Later rounds: previous global checkpoint"]
    CO --> G

    subgraph HOSPITALS["Three simulated hospital clients — separate local workspaces"]
        H1["Hospital 1<br/>Own train / validation images<br/>Local FedProx → checkpoint .pt"]
        H2["Hospital 2<br/>Own train / validation images<br/>Local FedProx → checkpoint .pt"]
        H3["Hospital 3<br/>Own train / validation images<br/>Local FedProx → checkpoint .pt"]
    end
    G --> H1
    G --> H2
    G --> H3
    H1 --> UP["Upload local checkpoints<br/>Obtain CIDs and SHA-256 digests"]
    H2 --> UP
    H3 --> UP
    UP --> IPFS[("Isolated local IPFS / Kubo<br/>Checkpoints and validation reports<br/>IPFS Desktop views stored files")]
    UP --> PV["Peer validation<br/>Each update evaluated by both other hospitals<br/>On each reviewer's own validation data"]
    PV --> DEC{"Both peers approve?<br/>Balanced accuracy > 0.5<br/>and ≥ incoming-global baseline"}
    DEC -->|"No"| REJ["Record rejection and reason<br/>Exclude update from aggregation<br/>Keep uploaded artifact and audit history"]
    DEC -->|"Yes"| ACCEPT["Eligible updates<br/>Admin reviews and approves aggregation"]
    AP -.-> ACCEPT
    ACCEPT --> FETCH["Retrieve accepted checkpoints from IPFS<br/>Verify committed CID / digest and parent model"]
    IPFS --> FETCH
    FETCH --> AGG["Off-chain validation-aware aggregation<br/>Weight ∝ training samples × mean peer balanced accuracy<br/>All rejected: retain incoming global model"]
    REJ -.->|"All rejected"| AGG
    AGG --> NEW["New / retained global checkpoint<br/>Upload to IPFS and publish global CID / digest"]
    NEW --> IPFS
    NEW --> EVAL["Evaluate global model on hospital validation sets<br/>Best round selected by pooled validation balanced accuracy"]
    EVAL --> NEXT{"More registered rounds?"}
    NEXT -->|"Yes: distribute global model"| G
    NEXT -->|"No"| PRED["Versioned global model and research prediction UI<br/>NORMAL / PNEUMONIA<br/>Uploaded image processed in memory"]

    CHAIN[("Local Ethereum / Hardhat<br/>HospitalDirectory: membership<br/>ClientAuthorization: delegated consent<br/>FederatedProtocolRegistry: rounds, CIDs,<br/>digests, peer decisions and global versions")]
    AP -.->|"Hospital authorization"| CHAIN
    HP -.->|"Signed client authorization"| CHAIN
    UP -.->|"Update CID, digest and sample count"| CHAIN
    PV -.->|"Review decisions and report evidence hashes"| CHAIN
    PV -->|"Validation report JSON"| IPFS
    NEW -.->|"Global CID, digest and aggregation evidence hash"| CHAIN
    CHAIN --> EX["Independent Blockscout explorer<br/>Blocks, transactions, receipts and contract records"]
    CO -.-> DASH["Admin / hospital dashboards<br/>Role-based progress, metrics, submissions and audit views"]
    CHAIN -.-> DASH
    IPFS -.-> DASH
```

## How to read it

- **Solid arrows:** model, report or workflow flow. **Dashed arrows:** authorization, evidence or monitoring.
- **FedProx is local training.** The coordinator performs the separately documented validation-aware aggregation off-chain; Solidity does not train or average model tensors.
- For accepted update `i`, `weight_i = (n_i × mean_peer_balanced_accuracy_i) / sum_accepted(n_j × mean_peer_balanced_accuracy_j)`. Rejected updates have zero weight. Invalid or missing reviews reject the update.
- Each peer compares a candidate with the incoming global model on the same private validation partition. Test images do not determine acceptance, weights or best-round selection.
- IPFS stores model files and report JSON. Blockchain stores references, digests and attestations. Peer-report CIDs are retained in project artifacts; the peer-review transaction commits the report hash, not its CID directly.
- Raw X-rays stay in hospital workspaces and are not uploaded to IPFS or blockchain. Model sharing alone does not provide formal privacy guarantees.

## Main implementation files

| Layer | Files |
|---|---|
| Portals, membership and campaigns | `project_dashboard.py`, `hospital_management.py`, `portal_workflow.py` |
| Campaign orchestration | `round_coordinator.py` |
| Local hospital execution | `portal_workers.py`, `hospital_workers.py`, `fedprox_core.py` |
| Peer acceptance and aggregation policy | `peer_policy.py`, `architecture_protocol.json` |
| IPFS and integrity checks | `architecture_io.py` |
| Smart contracts | `blockchain/contracts/HospitalDirectory.sol`, `ClientAuthorization.sol`, `FederatedProtocolRegistry.sol` |
| Independent explorer | `blockchain/blockscout/` |

See [portal workflow](PORTAL_WORKFLOW_GUIDE.md) for operation and [project context](../PROJECT_CONTEXT.md) for experiment history and remaining limitations. This is a research prototype, not a clinical diagnostic system.
