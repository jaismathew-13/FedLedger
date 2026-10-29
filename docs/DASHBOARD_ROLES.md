# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Separate dashboard roles

## Hospital users

Open http://127.0.0.1:8765/hospital (also the default root page).

Wallet sign-in, hospital application, own status/readiness and heartbeat. Approved hospitals with current on-chain authorization can use prediction and model version selection. Pending/rejected/suspended hospitals cannot access inference. No other hospitals' records, review reasons, logs, admin controls or cross-hospital monitoring are returned to hospital users. Sign-out revokes the wallet session server-side.

## Administrator

Open http://127.0.0.1:8765/admin. Sign in with the local token from local_operations/admin.key. The token stays in browser memory, is not placed in URLs or localStorage, and is never printed by the service.

Access: project overview, cross-hospital FL monitoring, validation performance/history, blockchain explorer, model/report integrity audits, prediction, organization approvals/rejections/suspension, live directory reconciliation, future enrollment and administration audit trail. Sign-out clears browser credentials. The local administrator token is a shared development credential, not an enterprise identity provider.

## Server enforcement

- /api/blocks, /api/snapshot, /api/chain, /api/log, /api/audit and /api/verify: administrator token required.
- /api/hospitals/admin, /decision and /roster: administrator only.
- /api/hospitals/me, /register and /heartbeat: wallet session required; registration/heartbeat have their additional membership checks.
- /api/hospitals now returns only the caller's own profile, not the hospital directory.
- /api/model and /api/predict: administrator or approved wallet with current on-chain authorization.
- No role is granted merely by opening an URL or hiding/showing a component.

The server is loopback-only. No training/contract changes were made for this interface split. Python and JavaScript syntax checks passed; new role flows have not been exercised end to end. Previously saved integration results predate these access-control changes. The startup helper now authenticates its own run-identity check with the local administrator credential.
