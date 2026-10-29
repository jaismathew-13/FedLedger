# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Ethereum model registry prototype

## Current scope

`contracts/ModelRegistry.sol` records an authorized publisher's checkpoint SHA-256, manifest SHA-256, run identifier and selected round. Entries cannot be overwritten. The deployer controls publisher authorization. Solidity events provide an audit trail. Model training, aggregation, prediction, and artifact storage stay off-chain.

This is an audit registry, not decentralized training coordination, peer validation, or proof of correct training. It provides no clinical or privacy guarantee. No images, patient IDs, paths, accuracy metrics or model weights are sent to this contract. A registration alone does not establish file availability.

## Prepare a real checkpoint

Training is needed at this milestone: creating the first real model registration and enabling predictions. Until then the contract can be developed independently. Do not manufacture a trained checkpoint or report placeholder hashes as a trained model.

After a completed run, stop training before hashing the artifacts so they cannot change during preparation. From the VS Code PowerShell terminal:

```powershell
& 'D:\dataset\.venv_runtime\Scripts\python.exe' 'D:\dataset\blockchain\prepare_registration.py' --run-dir 'D:\dataset\fedprox_outputs\YOUR_RUN' --output-dir 'D:\dataset\blockchain\registrations\YOUR_RUN'
```

This writes an off-chain manifest and `registration.json`, containing the four arguments to `registerModel`. `runId` is SHA-256 of the exact `run_config.json` bytes. Keep registration outputs with the corresponding frozen checkpoint. Do not hand-edit manifest bytes after hashing. The preparer hashes artifacts but does not load the checkpoint or establish its scientific validity.

## Development deployment

The contract has been compiled with solc 0.8.30 targeting Shanghai and deployed to local Hardhat 3.20.0, chain ID 31337. Address, ABI, deployment receipt, instance identity, genesis hash and deployed-code hash are saved in `deployment.hardhat.local.json`. The node binds only to `127.0.0.1:8545`. No public network or real funds are involved. Hardhat config is `hardhat.config.js` (ES modules). The compile helper uses pinned solc-js directly; the node is provided by Hardhat 3.

`registry.py` implements deployment, status, publisher authorization, registration receipts and local-file verification against the contract. It is restricted to local Hardhat chain ID 31337 and uses unlocked development accounts; external wallet and public-network integration are not implemented. It checks saved Hardhat instance identity, chain identity and deployed-code hash before using a deployment. Registration is explicit after a run is finished, so training does not depend on blockchain availability. Only compare digests with the same SHA-256 algorithm; these bytes32 values are not Ethereum keccak256 digests.

References: [Solidity contracts and events](https://docs.soliditylang.org/en/latest/contracts.html), [Remix documentation](https://remix-ide.readthedocs.io/en/latest/).

## Installed local toolchain

Python packages use `.venv_runtime`. Node.js/npm live under `.tools` and Ethereum packages under `blockchain/node_modules`; no global Node installation is required. Exact versions are recorded in `requirements-lock.txt`, `.tools/node-runtime.json`, and `blockchain/package-lock.json` when installation completes.

From the VS Code terminal:

```powershell
.\blockchain\tools.ps1 versions
.\blockchain\tools.ps1 compile
.\blockchain\tools.ps1 chain
```

The chain command starts a Hardhat 3 development node on localhost only (`hardhat node --hostname 127.0.0.1 --port 8545`). Stop it with Ctrl+C. These are deterministic, publicly known development accounts; never fund them with real assets. The compiler script targets the same Shanghai hardfork as the node. The launcher restores PATH when it exits. For a background node, `start_chain.ps1` saves its PID and logs and refuses to start a duplicate on an occupied port. Do not launch the foreground chain while the background node is running.

Hardhat node state is in memory and is lost on restart. After restarting the node, run `registry.py deploy`: it archives the prior instance deployment to `deployment-history/` and deploys a new registry. Previously registered model files must be registered again on the new chain instance. Keep their original receipts; prepare a new registration folder for republication. The verifier refuses stale instance metadata. Old Ganache data and deployment evidence remain archived; the active workflow does not use them.

To reinstall Python dependencies, install CUDA wheels as described in the root README, then use `pip install -r requirements.txt`. The lock file records the full currently installed environment; restoring it requires the CUDA wheel index for its PyTorch entries.

## Python workflow

See `PROJECT_STATUS.md` in the project root for the current stop point. Run from the project root in VS Code:

```powershell
# Inspect the actual local deployment; no training.
.\.venv_runtime\Scripts\python.exe blockchain\registry.py status

# After training: replace YOUR_RUN with the real completed run directory.
.\.venv_runtime\Scripts\python.exe blockchain\prepare_registration.py --run-dir fedprox_outputs\YOUR_RUN --output-dir blockchain\registrations\YOUR_RUN
.\.venv_runtime\Scripts\python.exe blockchain\registry.py register --registration-dir blockchain\registrations\YOUR_RUN --run-dir fedprox_outputs\YOUR_RUN
.\.venv_runtime\Scripts\python.exe blockchain\registry.py verify --registration-dir blockchain\registrations\YOUR_RUN --run-dir fedprox_outputs\YOUR_RUN
```

The verifier checks all manifest-listed artifact hashes and both on-chain hashes; it exits with an error on mismatch or missing registration. The contract rejects duplicate run/round entries. Stop training before preparing a registration and preserve its exact files. `authorize --address 0x...` grants an address publisher access; add `--revoke` to remove it. The current publishing command uses the local coordinator account. This is a single-coordinator audit prototype, not independently operated hospital nodes.

The active dependency is Hardhat 3; Ganache was removed from package.json and the lockfile. The initial Ganache npm audit findings are historical and are not a current Hardhat audit report. This chain remains local development infrastructure. No contract security tests or independent audit have been run. Reference: [Hardhat local node documentation](https://hardhat.org/docs/guides/hardhat-node).
