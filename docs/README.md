# Project guides

Start with [Project context](../PROJECT_CONTEXT.md) for the full system explanation.

| Guide | Use |
|---|---|
| [Blockscout explorer](BLOCKSCOUT.md) | Independent visual explorer for the local Hardhat chain |
| [Hospital and admin workflow](PORTAL_WORKFLOW_GUIDE.md) | Current onboarding, local data setup and campaigns |
| [Operations](../OPERATIONS.md) | Service startup and blockchain lifecycle |
| [Results](../RESULTS.md) | Historical experiment conclusions |
| [Dashboard features](DASHBOARD_FEATURES.md) | Feature coverage |
| [Dashboard roles](DASHBOARD_ROLES.md) | Admin and hospital access |
| [Architecture](ARCHITECTURE.md) | Architecture documentation |
| [Architecture guide](ARCHITECTURE_GUIDE.md) | Experiment architecture workflow |
| [Integration guide](INTEGRATION_GUIDE.md) | Integration reference |
| [Demo guide](DEMO_GUIDE.md) | Earlier demonstration workflow |
| [Protocol decisions](PROTOCOL_DECISIONS.md) | Registered protocol decisions |
| [Project status](PROJECT_STATUS.md) | Development history and status |
| [Earlier hospital onboarding](HOSPITAL_ONBOARDING.md) | Historical reference; superseded by the current workflow |

## Folder layout

- Project root: active Python modules, dashboard assets, configuration, requirements and primary entry documents.
- `docs/`: detailed guides.
- `reports/data_quality/`: original and patient-split leakage reports.
- `reports/maintenance/`: cleanup manifests with original paths and hashes.
- `blockchain/`: contracts, adapters and local chain dependencies.
- `ipfs/`: local storage-service helpers.
- `local_operations/`: hospital registrations, private client state and campaign data.
- `architecture_outputs/`, `fedprox_outputs/`, `multiseed_outputs/`: preserved model outputs and evidence.
- `archive/`: retired workflows and the unused earlier single-dashboard page.
- Dataset directories: preserved in their original locations.

Active Python modules remain in the root because their imports and runtime paths depend on that layout. Model caches, virtual environments, IPFS repository data and blockchain dependencies are not disposable project clutter.

After reboot: [Startup commands](STARTUP.md).

Judge demonstration: [Independent blockchain verification](BLOCKCHAIN_VERIFICATION.md).
