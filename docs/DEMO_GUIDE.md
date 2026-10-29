# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Demonstration and presentation guide

## Demonstration sequence

1. Run ` .\.venv_runtime\Scripts\python.exe start_project.py ` from D:\dataset. Keep the existing Hardhat node running. Open http://127.0.0.1:8765.
2. Overview: show the completed run, algorithm, latest version and chain connection. Explain best checkpoint versus latest version.
3. Monitor: select a round with accepted updates and one with all rejected. Explain two independent peer decisions and retained global behavior.
4. Performance: inspect validation curves, best-round selection and plateau. State that no independent external accuracy is established.
5. IPFS Desktop: Files > training > run_20261020T093433_860908Z. Open a round to show hospital/global model references. These are model files, not raw X-rays.
6. Explorer: filter the same round, load live details, inspect a receipt/block number, timestamp and CID. Cards represent actual run receipts; unrelated blocks are omitted.
7. Audit: verify round/client. Show model CID, committed and recalculated hashes, local validation evidence hashes and final acceptance decision.
8. Prediction: use a public demonstration X-ray, choose best model, predict, then another saved version. Explain scores are uncalibrated; inference is not diagnosis. Prediction images/results stay out of blockchain.

## Presentation outline

- Problem and research objective: distributed pneumonia classification with auditable model updates.
- Data preparation: patient grouping, exact deduplication, original images preserved.
- Architecture: local FedProx, local IPFS transport, peer validation, chain commitments and adaptive off-chain aggregation.
- Implementation: simulated clients on one GPU; localhost services; full local model state artifacts.
- Results: show RESULTS.md and actual validation curves; explain rejected rounds and retained model.
- Demonstration: trace a client CID through a receipt to a verified global checkpoint and prediction.
- Limitations: independence, one seed, inferred patient IDs, local development chain and no clinical/privacy/robustness guarantees.
- Future work: obtain valid external data, patient-cluster uncertainty and pre-registered replication.

## Likely questions

**Does blockchain store images?** No. It records model references, hashes, peer decisions and evidence hashes.

**Does IPFS guarantee privacy?** No. This demonstration uses an isolated local node. Model updates can still expose information; no formal privacy guarantee is claimed.

**Why many rejections?** Candidates often failed to match the incoming global on at least one reviewer's validation set; both approvals are required.

**Why no FedAvg chart?** The current experiment is FedProx-only; no comparison data are invented.

**Is the final accuracy independently validated?** No; current main metrics are validation results and proposed external data showed content overlap.
