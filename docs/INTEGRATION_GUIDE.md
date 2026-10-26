# Local project interface

Start from D:\dataset:

```powershell
.\.venv_runtime\Scripts\python.exe -u project_dashboard.py --run-dir architecture_outputs/run_20261020T093433_860908Z
```

Open http://127.0.0.1:8765. The selected best model is frozen; uploaded images are processed in memory and not saved. Upload an actual chest X-ray. Predictions are research outputs, not clinical diagnoses. Live verification needs the original Hardhat instance and local IPFS node running. Resetting Hardhat invalidates live provenance verification for that run.

## Independent evaluation (pending new dataset)

Prepare a CSV with columns `path,patient_id,label`. Labels must be NORMAL or PNEUMONIA. Relative image paths resolve against the CSV directory. Confirm that patients are independent of all prior training/validation patients using source provenance; filename IDs across unrelated sources cannot establish independence automatically. Do not tune the model or threshold on this dataset. Review cross-dataset duplicates and patient leakage before running.

```powershell
.\.venv_runtime\Scripts\python.exe evaluate_independent.py --run-dir architecture_outputs/run_20261020T093433_860908Z --manifest PATH_TO_MANIFEST.csv --independence-confirmed
```

The command uses the selected model unchanged and writes metrics and per-image predictions under multiseed_outputs/independent. It does not train or choose a new threshold. Patient-cluster uncertainty estimation is still needed for a defensible final report. No independent dataset has been evaluated yet.
