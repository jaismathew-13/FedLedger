"""Evaluate a frozen model on a user-approved independent patient manifest."""
import argparse
import csv
import json
from pathlib import Path

from architecture_io import sha256, write_json
from progress_display import ProgressBar
from train_fedprox import record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True,
                        help='CSV columns: path,patient_id,label; label NORMAL or PNEUMONIA')
    parser.add_argument('--independence-confirmed', action='store_true',
                        help='Confirm patients are independent of training/validation; IDs alone cannot prove this.')
    parser.add_argument('--image-level-unverified', action='store_true', help='Report image-level results without claiming patient independence.')
    args = parser.parse_args()
    if not args.independence_confirmed and not args.image_level_unverified:
        parser.error('Confirm dataset independence after reviewing its provenance and patient IDs.')
    import torch
    import fedprox_core as fl
    from torch.utils.data import DataLoader
    torch.set_num_threads(2)
    reference = json.loads((args.run_dir/'best_global_reference.json').read_text())
    checkpoint = args.run_dir/'best_model.pt'
    if sha256(checkpoint) != reference['sha256']:
        raise ValueError('Frozen checkpoint hash mismatch.')
    rows = list(csv.DictReader(args.manifest.open(encoding='utf-8-sig')))
    pairs, patients, seen = [], set(), set()
    for row in rows:
        path = Path(row['path'])
        path = path if path.is_absolute() else args.manifest.parent/path
        if (not row['patient_id'].strip() and not args.image_level_unverified) or row['label'] not in fl.CLASS_FOLDERS or not path.is_file():
            raise ValueError('Every image requires an existing path, patient ID and supported label.')
        digest = sha256(path)
        if digest in seen:
            raise ValueError('Duplicate image bytes within independent manifest.')
        seen.add(digest)
        if row['patient_id'].strip():
            patients.add(row['patient_id'])
        pairs.append((str(path), fl.CLASS_FOLDERS[row['label']]))
    if {label for _, label in pairs} != {0, 1}:
        raise ValueError('Both classes are required.')
    saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
    model = fl.build_model(False)
    model.load_state_dict(saved['model_state_dict'])
    loader = DataLoader(fl.PneumoniaDataset(pairs, fl.eval_transform), batch_size=fl.BATCH_SIZE,
                        shuffle=False, num_workers=0)
    with ProgressBar(loader, desc='Independent evaluation', unit='batch') as batches:
        loss, true, predicted, scores = fl.evaluate(model, batches, 'cpu')
    output = Path('multiseed_outputs')/'independent'/sha256(args.manifest)[2:]
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'metrics.json', {'metrics': fl.compute_metrics(true, predicted, scores),
        'loss': loss, 'images': len(pairs), 'patients': None if args.image_level_unverified else len(patients),
        'evaluation_scope': 'image_level_patient_independence_unverified' if args.image_level_unverified else 'operator_confirmed_patient_independence',
        'checkpoint_sha256': reference['sha256'], 'manifest_sha256': sha256(args.manifest),
        'decision_rule': 'argmax; NORMAL wins ties',
        'limitations': 'Patient IDs unavailable; no patient-wise independence or patient-cluster uncertainty established.' if args.image_level_unverified else 'Patient independence confirmed by operator; uncertainty estimates require patient-cluster resampling, not image-wise intervals.'})
    with (output/'predictions.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['path', 'patient_id', 'true_label', 'predicted_label', 'pneumonia_score'])
        for row, pair, truth, prediction, score in zip(rows, pairs, true, predicted, scores):
            writer.writerow([pair[0], row['patient_id'], int(truth), int(prediction), float(score)])
    record(f'Independent evaluation completed: manifest={args.manifest}; frozen model={reference["sha256"]}; output={output}')
    print(output)


if __name__ == '__main__':
    main()
