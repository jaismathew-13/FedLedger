# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Standalone Blockscout explorer

See [the setup guide](../../docs/BLOCKSCOUT.md).

Source: https://github.com/blockscout/blockscout

Official Docker configuration checked out at commit
`9cd48cc0708d520f093ec8a8c37d9a998b258171` in `upstream/`.
Our compose file adapts the official Hardhat configuration for localhost port4000,
named database volumes, and a smaller stack: PostgreSQL, Redis, Blockscout backend,
Blockscout frontend and nginx. Optional statistics charts, contract verification,
signature lookup, and UML services are disabled. The explorer still indexes actual
blocks, transactions, receipts, addresses and logs from the running Hardhat node.

Container images currently use upstream release-channel tags. After the first
successful launch, record the actual image IDs/digests with the verification record.
The stack was verified against live RPC on27October2026. Exact image digests and block/receipt comparisons are saved in multiseed_outputs/blockscout/live_verification.json.

The downloaded upstream checkout is ignored by the project repository. To restore:

```powershell
git clone --depth 1 --filter=blob:none --sparse https://github.com/blockscout/blockscout.git blockchain/blockscout/upstream
git -C blockchain/blockscout/upstream fetch --depth 1 origin 9cd48cc0708d520f093ec8a8c37d9a998b258171
git -C blockchain/blockscout/upstream checkout 9cd48cc0708d520f093ec8a8c37d9a998b258171
git -C blockchain/blockscout/upstream sparse-checkout set docker-compose
```
