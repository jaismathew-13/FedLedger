"""Patient-wise allocation of existing validation images; no copying or re-split."""
from collections import defaultdict
import random
from pathlib import Path

from architecture_io import write_json
from patient_split_check import patient_id


def prepare_hospitals(dataset_root, output, seed):
    import fedprox_core as fl
    root = Path(dataset_root)
    train = fl.load_split_pairs(str(root/'train'))
    validation = fl.load_split_pairs(str(root/'val'))
    train_ids = {patient_id(Path(path), 'train', root)[0] for path, _ in train}
    groups = defaultdict(list)
    for path, label in validation:
        identity, _ = patient_id(Path(path), 'val', root)
        if identity in train_ids:
            raise ValueError('Train/validation patient overlap; refusing the architecture run.')
        groups[identity].append((path, label))
    rng = random.Random(seed)
    ordered = list(groups.items())
    rng.shuffle(ordered)
    ordered.sort(key=lambda item: -len(item[1]))
    bins = [[], [], []]
    counts = [[0, 0] for _ in bins]
    totals = [sum(label == c for _, label in validation) for c in (0, 1)]
    patient_assignments = {}
    for identity, pairs in ordered:
        group_counts = [sum(label == c for _, label in pairs) for c in (0, 1)]
        # Minimize incremental squared class-count imbalance; deterministic tie breaks.
        hospital = min(range(3), key=lambda h: (sum(
            ((counts[h][c] + group_counts[c]) ** 2 - counts[h][c] ** 2) / max(1, totals[c])
            for c in (0, 1)), len(bins[h]), h))
        bins[hospital].extend(pairs)
        patient_assignments[identity] = hospital
        for c in (0, 1):
            counts[hospital][c] += group_counts[c]
    if any(min(values) == 0 for values in counts):
        raise ValueError('Each hospital validation partition must contain both classes.')
    clients = fl.partition_realistic_hospitals(train, seed, fl.CLIENT_PROFILES,
        int(0.5 * len(train) / 3), fl.PREVALENCE_NOISE_STD, fl.PREVALENCE_CLIP)
    flat = [path for client in clients for path, _ in client]
    if len(flat) != len(set(flat)) or set(flat) != {path for path, _ in train}:
        raise ValueError('Hospital training partitions must cover each training image exactly once.')
    manifests = []
    summary = []
    for hospital in range(3):
        folder = Path(output)/'hospitals'/f'hospital_{hospital}'
        path = folder/'data_manifest.json'
        write_json(path, {'hospital_id': hospital, 'name': fl.CLIENT_PROFILES[hospital]['name'],
                          'train': clients[hospital], 'val': sorted(bins[hospital]),
                          'validation_patient_ids': sorted(k for k, h in patient_assignments.items() if h == hospital)})
        manifests.append(str(path))
        summary.append({'hospital_id': hospital, 'training_images': len(clients[hospital]),
                        'validation_images': len(bins[hospital]), 'val_class_counts': counts[hospital],
                        'validation_patients': sum(h == hospital for h in patient_assignments.values())})
    write_json(Path(output)/'partition_summary.json', summary)
    return manifests, validation
