# Target architecture supplied by the user

The user's flowchart is the target design. Existing artifacts are evidence for the earlier prototype and must not be described as having executed the full architecture.

## Traceability

The table below preserves the gap assessment made when the flowchart was first supplied. Those missing components are now implemented in a separate full-protocol entry point; see `ARCHITECTURE_GUIDE.md` for current code, services, artifact layout and unexercised paths. The completed prototype has not been relabeled as a full-protocol run.

| Diagram component | Current implementation | Required work |
|---|---|---|
| Public chest X-rays, preprocessing, patient-disjoint splits | Implemented; originals preserved | Retain patient separation and untouched final external holdout |
| Three simulated non-IID hospitals | Implemented as partitions in one process | Separate each hospital's artifacts and validation partition |
| Initial ResNet-18, distribute global weights | Implemented in memory | Track the exact input global version for every hospital update |
| FedProx local training, in parallel | Local FedProx implemented; hospitals execute sequentially on one GPU | Decide actual parallel worker/resource execution before claiming parallelism |
| Each hospital generates a local .pt update | Current local states are temporary and not saved | Save a versioned local state checkpoint for every hospital and round |
| Upload local updates to IPFS, receive CIDs | Not implemented | Add IPFS service, add/pin/retrieve operations, digest and serialization checks |
| Cross-hospital peer validation on private validation data | Not implemented; current validation is central | Define patient-disjoint hospital validation allocations, peer assignment and acceptance rule |
| Reject failed updates | Not implemented | Persist decision and reason; exclude rejected updates; define all-rejected behavior |
| Record round/client/CID/validation result on blockchain | Current contract records a final global model hash | Add a new protocol contract with hospital identities, authorized peer attestations and round/update records |
| Retrieve accepted updates from IPFS | Not implemented | Bind retrieval to accepted on-chain records and verify checkpoint content |
| Off-chain validation-aware adaptive aggregation | Current aggregation uses sample counts only | Specify a mathematical weighting rule before implementation; freeze it before seeing results |
| New ResNet-18 global model | Implemented for the earlier aggregation rule | Generate only from the full protocol's accepted updates |
| Global model on IPFS with on-chain CID | Not implemented | Store/pin each global checkpoint and register its CID/version |
| Redistribute global model and repeat | In-memory loop implemented | Retrieve/verify the published global version at hospital boundaries |

## Artifact contract to implement

Each hospital will have local checkpoint files, for example `architecture_outputs/RUN/hospitals/HOSPITAL/round_0001/local_model.pt`. These do not exist for the completed prototype. Each update record must bind run ID, round, hospital identity, input global version, checkpoint digest, IPFS CID and sample count. No raw images or patient identifiers belong in these records.

Peer decisions must bind the exact update/CID being reviewed, the different validating hospital's identity, validation metric, acceptance decision and rule version. The on-chain contract can authenticate who submitted a decision but cannot establish that the hospital evaluated honestly.

The diagram's local model updates will initially be treated as full model state checkpoints, consistent with the existing trainer, unless a parameter-delta format is explicitly chosen. CIDs and SHA-256 are distinct identifiers and must not be substituted for one another.

## Scientific decisions still required

Update: the user delegated the rule choice. Peer acceptance, weighting and validation-allocation choices are now recorded in `PROTOCOL_DECISIONS.md` and `architecture_protocol.json`. The list below is the original decision inventory; parallel execution feasibility remains unresolved, and the declared choices still require protocol integration.

- Peer selection: which different hospital evaluates each update, and how many peers are required?
- Private validation: allocation of patient-disjoint validation patients to each hospital and whether a separate central selection set remains available.
- Acceptance: metric, threshold or baseline comparison, tie handling and behavior when peers disagree.
- Adaptive aggregation: exact formula for combining sample counts and validation signals, including normalization and edge cases.
- All-rejected rounds: retain the prior global model or another explicitly registered rule.
- Parallel execution: actual resource configuration for hospital workers on the laptop.

Do not infer an acceptance threshold or tune the formula from existing test or validation scores. The user's earlier runbook prohibited unannounced aggregation and scientific-protocol changes. This architecture requires an explicit documented protocol amendment; the FedProx local loss need not change.

## Implementation order

1. Resolve and freeze peer-validation and aggregation rules.
2. Add per-hospital local checkpoints and private validation allocations.
3. Add local IPFS storage/retrieval and a new blockchain protocol contract.
4. Connect peer decisions, accepted-update retrieval, aggregation and global redistribution.
5. Run the complete protocol as a separately labeled experiment after announcing runtime.

Local-only development comes first. Uploading model updates to public IPFS is not authorized by this document. Model weights can expose training information; this architecture alone does not provide differential privacy, secure aggregation, clinical validation or Byzantine robustness.

## Completed prototype

The existing FedProx checkpoint and its hash registration remain valid artifacts of the earlier sample-weighted, centrally simulated run. They do not demonstrate IPFS, peer rejection, adaptive aggregation or parallel hospital execution. The missing historical local updates cannot be reconstructed from the final global checkpoint. A complete architecture run will require a new training run after the protocol is defined and implemented.
