"""Report patient IDs that occur in more than one dataset split.

Recognized names include person<N>_(bacteria|virus)_<M> and
NORMAL2-IM-<N>-... / IM-<N>-... . Unparsed filenames are treated as unique
patients, as required by the project runbook.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path


DEFAULT_DATASET_ROOT = Path(r"D:\dataset")
SPLITS = ("train", "val", "test")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
PERSON_RE = re.compile(r"person(?P<patient>\d+)_(?:bacteria|virus)_\d+", re.IGNORECASE)
IM_RE = re.compile(r"(?:NORMAL2-)?IM-(?P<patient>\d+)(?:-|_)", re.IGNORECASE)


def patient_id(path: Path, split: str, dataset_root: Path) -> tuple[str, bool]:
    name = path.name
    match = PERSON_RE.search(name)
    if match:
        return f"person:{int(match.group('patient'))}", True
    match = IM_RE.search(name)
    if match:
        return f"im:{int(match.group('patient'))}", True
    relative = path.relative_to(dataset_root).as_posix().casefold()
    return f"unparsed:{relative}", False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    args = parser.parse_args()
    root = args.dataset_root.resolve()

    ids_by_split: dict[str, set[str]] = {}
    unparsed_by_split: dict[str, int] = {}
    for split in SPLITS:
        split_dir = root / split
        if not split_dir.is_dir():
            raise FileNotFoundError(f"Missing split directory: {split_dir}")
        ids: set[str] = set()
        unparsed = 0
        for path in sorted(split_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            identifier, parsed = patient_id(path, split, root)
            ids.add(identifier)
            if not parsed:
                unparsed += 1
        ids_by_split[split] = ids
        unparsed_by_split[split] = unparsed
        print(f"{split}: {len(ids)} patient IDs, {unparsed} unparsed image(s) treated as unique patients")

    print("\n== Patient overlap by split pair ==")
    pair_overlaps: dict[tuple[str, str], set[str]] = {}
    for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
        overlap = ids_by_split[left] & ids_by_split[right]
        pair_overlaps[(left, right)] = overlap
        print(f"{left} vs {right}: {len(overlap)} shared patient ID(s)")
        for identifier in sorted(overlap)[:10]:
            print(f"  {identifier}")

    any_multi_split = set().union(*pair_overlaps.values())
    print(f"\nDistinct patient IDs appearing in multiple splits: {len(any_multi_split)}")
    print("Done.")


if __name__ == "__main__":
    main()
