# Privacy Preserving Federated Learning for Multi-Institutional Pneumonia Prediction Using Blockchain

## Dashboard feature coverage

Open http://127.0.0.1:8765 and refresh to load the six sections. Uses the existing HTML/JavaScript and local Python service, without Streamlit.

1. Overview: hospital count, FedProx algorithm, completed rounds, latest saved global version, latest validation accuracy, live chain status, latest saved receipt status, progress and recent receipt activity. Refresh explicitly for updated data.
2. Federated monitor: round selector, hospital/backend IDs, local training/model artifacts, update submission, review counts, final decisions and reasons, accepted/rejected totals, aggregation state, error JSON and bounded log tails. Historical statuses derive from saved artifacts; this is not a live GPU batch telemetry service. Quiet logs may be empty.
3. Performance: eight per-round validation charts, full history table, best round, final global accuracy, measured round wall time. FedAvg comparison unavailable for this single-method run. Communication overhead was not measured. Validation metrics are not independent test results.
4. Explorer: actual saved receipt block cards, round filter, contract/network/chain ID, latest live block, transaction hashes/status, client/reviewer, round CID, decisions and full details. Explicit live refresh fetches timestamps, block hashes and parent hashes and checks receipt block/status. Cards omit unrelated blocks. Validation reports have committed SHA256 hashes, not recorded IPFS report CIDs.
5. Audit: selected round/client IPFS retrieval and SHA256 checks against live client/global commitments; local checkpoint checks; both peer report hashes compared to contract commitments; aggregation evidence hash; complete acceptance/CID timeline. This checks integrity, not truthfulness of reported metrics or clinical validity.
6. Prediction: image selection/preview, selected best or saved global version, argmax classification, uncalibrated scores, version/CID/checkpoint digest and UTC inference timestamp. Images and predictions are not persisted or submitted to blockchain. Clinical prototype disclaimer shown. Image must be an actual chest X-ray; input type cannot be established by the model.

## Checks

Python and JavaScript syntax checks passed. Snapshot, chain, live receipts and model APIs responded successfully. All saved receipt block/status checks passed on the current chain. A selected best-round client/global IPFS retrieval and both report/aggregation hash checks passed; see multiseed_outputs/dashboard_feature_checks.json. Browser visual checks and version-selection inference have not been exercised. Independent evaluation remains blocked by dataset overlap.

## Portal campaign extension

Separate hospital/admin views now include hospital-scoped local data, delegated client authorization, opted-in campaign execution, safe round controls, peer report CIDs, aggregation approval, feedback and export. See PORTAL_WORKFLOW_GUIDE.md. Latest tests use isolated fixtures; they are not new model accuracy. No unsupported FedAvg comparison was added.

## Shared dashboard layout
Both portals use dashboard_shell.css and dashboard_shell.js: role-aware sidebar, fixed top navigation, accessible hamburger toggle, mobile overlay/Escape dismissal, and consistent form/table/card styling. Authentication and campaign APIs are unchanged. Live assets and HTTP role checks passed; browser visual QA remains outstanding.

Browser button verification now uses check_dashboard_buttons.py with isolated Edge, simulated wallet and intercepted API fixtures. Tested both roles, navigation, mobile drawer, export, prediction, campaign buttons and empty-campaign restrictions. Real MetaMask extension signing and full hospital training remain separate integration exercises. Evidence: multiseed_outputs/dashboard_button_verification.json.

## Current-chain explorer (26 October 2026)

Admin sidebar > Blockchain explorer now displays live JSON-RPC blocks, starting with genesis where available. Includes contract deployments, hospital approval/suspension MembershipChanged events, DelegateAuthorized events and training-contract events. Refresh latest blocks, search by block number, filter hospital/client/training events and inspect transaction hashes, receipt status, timestamp, block/parent hashes and decoded event arguments. Paging is bounded to25 blocks by default with a server maximum100. Anonymous and hospital-user access to /api/current-blocks is denied. Historical saved experiment receipts remain under History and are not mixed with the current chain. No public Etherscan is required.

Examples on the verified current instance: RGRI approval block4, ASTER block8, SNRSE block10, BMH block11. These numbers belong to that instance; after a Hardhat reset, use the current-chain explorer rather than assuming old block numbers still apply.
