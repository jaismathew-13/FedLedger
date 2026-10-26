# Architecture protocol v1

The user delegated choosing peer-validation and adaptive aggregation settings. These decisions are fixed before any full-architecture run. The completed prototype's validation scores have already been seen: this is a prospective amendment, not a claim that the protocol was registered before the earlier prototype. No test performance is used to choose these rules. Machine-readable settings: `architecture_protocol.json`; decision/weight calculations: `peer_policy.py`.

## Chosen rules

- Three hospitals; each update is reviewed by both other hospitals. Self-review is forbidden. Both reviews must approve.
- Each reviewer evaluates the incoming global model and the candidate local model on the same private validation patients with deterministic evaluation preprocessing.
- Accept only if the candidate balanced accuracy is strictly above 0.5 and at least as high as the incoming global model at each peer. Allowed degradation is zero. A tie with baseline is accepted only above 0.5. Invalid/missing reviews or malformed/nonfinite model tensors reject the update.
- For accepted update i, let n_i be its hospital training image count, and s_i the equally weighted mean of its two peer balanced accuracies. Aggregate using w_i = n_i*s_i / sum_j(n_j*s_j), over accepted updates only. No exponent or extra tunable coefficient is introduced.
- If all updates are rejected, retain the incoming global model, record the rejected/no-update round, and continue the predeclared rounds. Do not relax thresholds after seeing results.
- Preserve the existing rounds, local epochs, seed, mu, architecture, optimizer, augmentation and FedProx loss for the initial architecture run. Patient-wise allocation of the existing validation set to hospitals uses fixed seed 42, approximate equal sizes and class stratification. Each hospital must have both classes. Existing train/val/test files remain unchanged; allocations are manifest files.
- Select the best global round on pooled validation balanced accuracy over exactly the original validation union, using first-round tie handling. The peer scores influence training, so this validation performance is a development measure, not independent final accuracy. The new external test dataset remains untouched.

## Why these choices

Balanced accuracy accommodates the hospitals' class imbalance. Reviewing against the incoming global model gives each peer a local reference. Two reviewers avoid choosing a single favorable peer. The linear weight is simple enough to describe and reproduce. These are defensible initial choices, not demonstrated optimal settings and not a published robustness guarantee. Strict acceptance can reject useful non-IID updates, stall learning or favor hospitals whose data resemble the validation populations. Repeated validation use can overfit the development set. Report these outcomes instead of changing the policy to force improvement.

FedProx specifies the proximal local-training method; this peer filter and adaptive weighting are a separate project extension. Source: [Federated Optimization in Heterogeneous Networks, MLSys 2020](https://proceedings.mlsys.org/paper_files/paper/2020/hash/1f5fe83998a09396ebe6477d9475ba0c-Abstract.html).

## Implementation status

The policy functions/configuration are now connected to `train_architecture.py`, the new parallel hospital workers, local IPFS transport and `FederatedProtocolRegistry.sol`. The contract is compiled/deployed and manifests prepared. No full-architecture training, policy tests or model IPFS uploads have run. Actual parallel GPU fit remains unmeasured. See `ARCHITECTURE_GUIDE.md`. This does not relabel or replace the already trained global checkpoint.

Runtime settings for the new entry point: three dedicated spawned worker processes, a 28% CUDA allocator limit per worker, and two CPU threads per process. Local stochastic streams are fixed as `42 + (round-1)*3 + hospital_id`; pooled validation runs on CPU to avoid a fourth GPU model. These are declared before the first architecture run; a resource failure aborts and never silently switches to sequential execution.
