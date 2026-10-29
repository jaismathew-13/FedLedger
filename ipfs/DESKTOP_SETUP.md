# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## IPFS Desktop connected to the project

IPFS Desktop now controls the same storage used by Python through a local API pointer. A separately managed project Kubo process runs the node, because Desktop cannot directly manage a private-swarm repo.

- Repository: `D:\dataset\.ipfs-local`
- API: `http://127.0.0.1:5002`
- Gateway: `http://127.0.0.1:8081`
- Binary: `D:\dataset\.tools\kubo\ipfs.exe` (pinned Kubo 0.43.1)
- Desktop controller: `D:\dataset\.ipfs-desktop-control` (API pointer only, no model storage).
- Kubo mode: isolated private swarm; **not** strict `--offline`.

Desktop's required bandwidth RPC and the Python adapter were checked against the same peer identity. The node has no connected peers, no swarm listening addresses, no bootstrap peers, no delegated routing/publishing and no mDNS. Public AutoConf/AutoTLS are disabled for this private node. A project-only swarm key and `LIBP2P_FORCE_PNET=1` keep it separate from public IPFS. Its bare `/p2p/PeerID` identifier is not a routable network address. CIDs are not publicly provided by this setup.

After a restart, first run `.\.venv_runtime\Scripts\python.exe architecture_services.py ipfs`, then open IPFS Desktop. Keep the project node running during architecture training. Do not start a second daemon for the same repository. Python uses `architecture_io.LocalIPFS` and checks the node identity, private-mode configuration and absence of peers. No endpoint or training-algorithm change was needed.

Models added by the Python API are pinned by CID. Pinning a CID does not automatically create a named entry in Desktop's Files (MFS) view; an empty Files view does not imply the pinned blocks are missing. No model files have been added during this connection setup. The new architecture run will add its local/global checkpoints; images are not uploaded.

## Preserved previous setup

The earlier Desktop repository `C:\Users\Shunz\.ipfs` and its files were left intact. Desktop is now pointed at the project repository; it has not merged or moved the old repository's contents. To use those older files again, switch repository configurations deliberately rather than copying internal datastore files.

Original Desktop settings are backed up at `archive/ipfs_desktop_transition/20261020T082453_554788Z/desktop-config.before.json`. Additional retry backups are in adjacent folders; those may already contain project settings. Current verified connection metadata is `ipfs/desktop-connection.json`.

Desktop configuration is `C:\Users\Shunz\AppData\Roaming\IPFS Desktop\config.json`: `ipfsConfig.path` points to the API controller directory, `--offline` was removed, and `binaryPath` selects the pinned project Kubo. Desktop was restarted. Launch-at-login preferences were not changed.

Why strict offline mode failed: the installed Web UI initializes its connection by calling `stats/bw`, which Kubo rejects in `--offline` mode. CORS permission alone therefore did not fix it. The isolated private-node setup preserves local storage while allowing that status RPC. The `offline-only.json` filename is retained for compatibility; its contents now explicitly say `offline_only: false` and `mode: private-no-peers`.

The native computer-use helper was unavailable, so the change was applied through the application's documented saved configuration with approved process/filesystem access. Live node/process identity was verified; the GUI itself could not be visually inspected. `connect_desktop.py` records its changes/errors and makes backups before reconfiguration; rerunning it restarts Desktop and interrupts current IPFS operations, so do not run it during training.
