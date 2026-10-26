# Project results

## Registered experiment

ResNet-18, FedProx with mu 0.01, seed 42, three local epochs, twenty rounds, three simultaneous simulated hospitals. Patient-wise copied dataset; training/validation manifests and policy are preserved in architecture_outputs/run_20261020T093433_860908Z. All model selection uses pooled validation balanced accuracy, first round on ties. No independent test result is established. The test set was not used to choose this model.

## Selected model

Selected round: 11. Validation accuracy 0.987005; balanced accuracy 0.987005; sensitivity 0.986967; specificity 0.987044; precision 0.986967; F1 0.986967; ROC-AUC 0.998578. Confusion counts: TP 833, FN 11, FP 11, TN 838. These are validation metrics, not independent final accuracy.

## Peer rejection findings

Both other hospitals must approve. Each evaluates the candidate and incoming global on its own fixed validation subset. Candidate balanced accuracy must exceed 0.5 and be at least baseline. Accepted mass is sample count multiplied by mean peer balanced accuracy, normalized across accepted updates.

8 updates accepted; 52 rejected. Of the saved peer reviews, 89 were below their local incoming-global baseline and 31 met approval conditions. All updates after the selected round were rejected, so the global model was retained unchanged. This is retention under the gate, not evidence of ongoing learning or convergence. The strict two-peer rule and heterogeneous validation subsets can block updates; these data do not prove relaxing the gate would improve performance. No policy changes were made after results.

## Limits and honest conclusions

The system completed its registered local run and records integrity can be checked against its original Hardhat instance and IPFS content. Single seed, single original dataset, inferred patient IDs, simulated hospitals, and validation-guided weighting/selection limit generalization. The local external Testing copy later showed near-copy overlap; its image-level metrics are preserved with a leakage warning and must not be called independent accuracy. No FedAvg comparison is available for this run. Communication overhead and patient-cluster uncertainty are not measured. No claim of clinical validity, formal privacy guarantees, Byzantine robustness or novelty is made. Blockchain attests recorded commitments; it does not establish honest validation or correct labels.

Evidence: multiseed_outputs/architecture/run_20261020T093433_860908Z/history.csv, validation_metrics.json, selection.json, results_review.json and rejection_analysis.json.

## Later dashboard smoke campaign: leakage review

Campaign34c72e51-c98a-4a99-be9a-a540dce32a35 completed one round and passed mechanical integrity checks. A subsequent review found a probable transformed radiograph crossing SNRSE train/validation under inferred IDs im95/im96. Its saved validation result remains smoke-test evidence and must not be treated as independent final accuracy. A separate reviewed v2 copy links those image families in training; no new evaluation is claimed. Review: D:\dataset\multiseed_outputs\campaign_leakage_review\20261022T080906_451339Z\REPORT.md. The earlier registered20-round experiment above is a separate run.
