"""Copy a byte-deduplicated, patient-wise split to <dataset_root>_patientsplit.

Patient IDs are parsed from person<N>_(bacteria|virus)_<M> and
NORMAL2-IM-<N>-... / IM-<N>-... filenames. Each unparsed image is its own
patient. Source images are only read; all output is written to a new folder.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DATASET_ROOT = Path(r"D:\dataset")
SPLITS = ("train", "val", "test")
CLASSES = ("NORMAL", "PNEUMONIA")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
PERSON_RE = re.compile(r"person(?P<patient>\d+)_(?:bacteria|virus)_\d+", re.IGNORECASE)
IM_RE = re.compile(r"(?:NORMAL2-)?IM-(?P<patient>\d+)(?:-|_)", re.IGNORECASE)


@dataclass(frozen=True)
class ImageRecord:
    path: Path
    source_split: str
    class_name: str
    digest: str
    patient: str
    parsed_patient: bool


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_patient(path: Path, dataset_root: Path, source_split: str) -> tuple[str, bool]:
    match = PERSON_RE.search(path.name)
    if match:
        return f"person:{int(match.group('patient'))}", True
    match = IM_RE.search(path.name)
    if match:
        return f"im:{int(match.group('patient'))}", True
    relative = path.relative_to(dataset_root).as_posix().casefold()
    return f"unparsed:{relative}", False


def collect_records(root: Path) -> tuple[list[ImageRecord], dict[str, Counter[str]]]:
    records: list[ImageRecord] = []
    original_counts = {split: Counter() for split in SPLITS}
    for split in SPLITS:
        split_dir = root / split
        if not split_dir.is_dir():
            raise FileNotFoundError(f"Missing split directory: {split_dir}")
        for class_name in CLASSES:
            class_dir = split_dir / class_name
            if not class_dir.is_dir():
                raise FileNotFoundError(f"Missing class directory: {class_dir}")
            for path in sorted(class_dir.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                patient, parsed = parse_patient(path, root, split)
                records.append(ImageRecord(
                    path=path,
                    source_split=split,
                    class_name=class_name,
                    digest=md5_file(path),
                    patient=patient,
                    parsed_patient=parsed,
                ))
                original_counts[split][class_name] += 1
    if not records:
        raise RuntimeError(f"No images found under {root}")
    return records, original_counts


def deduplicate(records: list[ImageRecord]) -> tuple[list[ImageRecord], list[dict[str, str]]]:
    # Prefer a deterministic copy from train, then val, then test when identical
    # bytes appear in multiple source splits.
    split_order = {split: index for index, split in enumerate(SPLITS)}
    ordered = sorted(records, key=lambda rec: (
        split_order[rec.source_split],
        CLASSES.index(rec.class_name),
        rec.path.as_posix().casefold(),
    ))
    kept_by_hash: dict[str, ImageRecord] = {}
    keepers: list[ImageRecord] = []
    removed: list[dict[str, str]] = []
    for record in ordered:
        keeper = kept_by_hash.get(record.digest)
        if keeper is None:
            kept_by_hash[record.digest] = record
            keepers.append(record)
            continue
        removed.append({
            "removed_path": str(record.path),
            "kept_path": str(keeper.path),
            "removed_split": record.source_split,
            "kept_split": keeper.source_split,
            "removed_class": record.class_name,
            "kept_class": keeper.class_name,
            "md5": record.digest,
            "class_conflict": str(record.class_name != keeper.class_name).lower(),
        })
    return keepers, removed


def assign_patients(
    records: list[ImageRecord],
    proportions: dict[str, float],
    seed: int,
) -> dict[str, str]:
    groups: dict[str, list[ImageRecord]] = defaultdict(list)
    for record in records:
        groups[record.patient].append(record)

    group_counts: dict[str, Counter[str]] = {
        patient: Counter(record.class_name for record in items)
        for patient, items in groups.items()
    }
    total_by_class = Counter(record.class_name for record in records)
    targets = {
        split: {class_name: total_by_class[class_name] * proportions[split] for class_name in CLASSES}
        for split in SPLITS
    }
    assigned_counts = {split: Counter() for split in SPLITS}
    assigned_groups: dict[str, str] = {}
    rng = random.Random(seed)
    tie_order = {patient: rng.random() for patient in groups}
    patients = sorted(
        groups,
        key=lambda patient: (-sum(group_counts[patient].values()), tie_order[patient], patient),
    )

    # Deterministic greedy assignment minimizes normalized squared deviation
    # from the original split proportions for each class, using patient groups
    # as indivisible units.
    for patient in patients:
        counts = group_counts[patient]
        scored: list[tuple[float, float, str]] = []
        for split in SPLITS:
            delta = 0.0
            for class_name in CLASSES:
                before = assigned_counts[split][class_name]
                after = before + counts[class_name]
                target = targets[split][class_name]
                scale = max(target, 1.0)
                delta += ((after - target) ** 2 - (before - target) ** 2) / scale
            scored.append((delta, rng.random(), split))
        chosen = min(scored)[2]
        assigned_groups[patient] = chosen
        assigned_counts[chosen].update(counts)

    # Ensure each split has at least one patient for each class when the
    # deduplicated data contains at least three distinct patient groups for it.
    for target_split in SPLITS:
        for class_name in CLASSES:
            if assigned_counts[target_split][class_name] > 0:
                continue
            candidates: list[tuple[int, str, str]] = []
            for patient, counts in group_counts.items():
                donor = assigned_groups[patient]
                if donor == target_split or counts[class_name] == 0:
                    continue
                donor_groups_of_class = sum(
                    group_counts[other][class_name] > 0
                    for other, current_split in assigned_groups.items()
                    if current_split == donor
                )
                if donor_groups_of_class <= 1:
                    continue
                preserves_donor_classes = all(
                    sum(
                        group_counts[other][other_class] > 0
                        for other, current_split in assigned_groups.items()
                        if current_split == donor
                    ) > 1
                    for other_class in CLASSES
                    if group_counts[patient][other_class] > 0
                )
                if preserves_donor_classes:
                    candidates.append((sum(counts.values()), patient, donor))
            if candidates:
                _, patient, donor = min(candidates)
                assigned_groups[patient] = target_split
                for class_name_to_move, amount in group_counts[patient].items():
                    assigned_counts[donor][class_name_to_move] -= amount
                    assigned_counts[target_split][class_name_to_move] += amount

    return assigned_groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    source_root = args.dataset_root.resolve()
    output_root = source_root.with_name(source_root.name + "_patientsplit")
    if output_root.exists():
        raise FileExistsError(
            f"Output already exists; refusing to overwrite it: {output_root}"
        )

    records, original_counts = collect_records(source_root)
    deduplicated, removed = deduplicate(records)
    source_totals = {split: sum(original_counts[split].values()) for split in SPLITS}
    source_total = sum(source_totals.values())
    proportions = {split: source_totals[split] / source_total for split in SPLITS}
    assignments = assign_patients(deduplicated, proportions, args.seed)

    output_root.mkdir(parents=True)
    for split in SPLITS:
        for class_name in CLASSES:
            (output_root / split / class_name).mkdir(parents=True, exist_ok=True)

    summary_counts = {split: Counter() for split in SPLITS}
    summary_patients: dict[str, set[str]] = {split: set() for split in SPLITS}
    summary_unparsed = Counter()
    split_order = {split: index for index, split in enumerate(SPLITS)}
    for record in sorted(deduplicated, key=lambda rec: (
        split_order[assignments[rec.patient]], rec.class_name, rec.path.as_posix().casefold()
    )):
        destination_split = assignments[record.patient]
        # Prefix source split to avoid overwriting same-named files from
        # different original split folders.
        destination_name = f"{record.source_split}__{record.path.name}"
        destination = output_root / destination_split / record.class_name / destination_name
        shutil.copy2(record.path, destination)
        summary_counts[destination_split][record.class_name] += 1
        summary_patients[destination_split].add(record.patient)
        if not record.parsed_patient:
            summary_unparsed[destination_split] += 1

    removed_path = output_root / "removed_duplicates.csv"
    removed_fields = [
        "removed_path", "kept_path", "removed_split", "kept_split",
        "removed_class", "kept_class", "md5", "class_conflict",
    ]
    with removed_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=removed_fields)
        writer.writeheader()
        writer.writerows(removed)

    summary_path = output_root / "split_summary.csv"
    summary_fields = [
        "split", "normal_images", "pneumonia_images", "total_images",
        "patient_count", "unparsed_images_treated_as_unique_patients",
    ]
    with summary_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=summary_fields)
        writer.writeheader()
        for split in SPLITS:
            normal = summary_counts[split]["NORMAL"]
            pneumonia = summary_counts[split]["PNEUMONIA"]
            writer.writerow({
                "split": split,
                "normal_images": normal,
                "pneumonia_images": pneumonia,
                "total_images": normal + pneumonia,
                "patient_count": len(summary_patients[split]),
                "unparsed_images_treated_as_unique_patients": summary_unparsed[split],
            })

    print(f"Source: {source_root}")
    print(f"Copied patient-wise split: {output_root}")
    print(f"Seed: {args.seed}")
    print(f"Original images: {len(records)}; byte-identical duplicates removed: {len(removed)}")
    print(f"Unparsed image filenames treated as unique patients: {sum(not r.parsed_patient for r in deduplicated)}")
    print("Original split proportions: " + ", ".join(f"{s}={proportions[s]:.6f}" for s in SPLITS))
    print("\nNew split counts:")
    for split in SPLITS:
        normal = summary_counts[split]["NORMAL"]
        pneumonia = summary_counts[split]["PNEUMONIA"]
        print(
            f"{split}: NORMAL={normal}, PNEUMONIA={pneumonia}, total={normal + pneumonia}, "
            f"patients={len(summary_patients[split])}, unparsed={summary_unparsed[split]}"
        )
    print(f"Reports: {removed_path}; {summary_path}")


if __name__ == "__main__":
    main()
