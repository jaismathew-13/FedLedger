"""
Check for data leakage between train/, val/ and test/.

1) Exact duplicates: identical file content (MD5 hash), regardless of file name.
2) Near duplicates (optional): visually identical images that were resized,
   re-saved or re-compressed, via perceptual hashing.

Usage:
    python check_leakage.py
Edit DATASET_PATH below. Near-duplicate check needs:  pip install imagehash
"""
import hashlib
import os
from collections import defaultdict

from PIL import Image

DATASET_PATH = r"D:\dataset_patientsplit"  # patient-wise split created for this run
SPLITS = ["train", "val", "test"]
EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
CHECK_NEAR_DUPLICATES = True        # set False to skip (slower)
PHASH_MAX_DISTANCE = 2              # 0 = identical hash; small values = near-identical


def list_images(split):
    out = []
    for root, _, files in os.walk(os.path.join(DATASET_PATH, split)):
        for f in files:
            if os.path.splitext(f)[1].lower() in EXTS:
                out.append(os.path.join(root, f))
    return out


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    files = {s: list_images(s) for s in SPLITS}
    for s in SPLITS:
        print(f"{s}: {len(files[s])} images")

    # ---- exact duplicates ----
    hashes = {s: defaultdict(list) for s in SPLITS}
    for s in SPLITS:
        for p in files[s]:
            hashes[s][md5(p)].append(p)

    print("\n== Exact duplicate check (file content) ==")
    for a, b in [("train", "val"), ("train", "test"), ("val", "test")]:
        common = set(hashes[a]) & set(hashes[b])
        print(f"{a} vs {b}: {len(common)} shared images")
        for h in list(common)[:5]:
            print(f"   e.g. {hashes[a][h][0]}  <->  {hashes[b][h][0]}")

    for s in SPLITS:
        dups = sum(1 for v in hashes[s].values() if len(v) > 1)
        print(f"duplicates inside {s}: {dups} content groups")

    # ---- near duplicates ----
    if CHECK_NEAR_DUPLICATES:
        try:
            import imagehash
        except ImportError:
            print("\nSkipping near-duplicate check (pip install imagehash to enable).")
            return

        print("\n== Near-duplicate check (perceptual hash) ==")
        ph = {}
        for s in SPLITS:
            ph[s] = []
            for p in files[s]:
                try:
                    ph[s].append((imagehash.phash(Image.open(p).convert("L")), p))
                except Exception:
                    pass

        for a, b in [("train", "val"), ("train", "test")]:
            # compare each val/test image against all train images
            n_hits = 0
            examples = []
            for hb, pb in ph[b]:
                for ha, pa in ph[a]:
                    if ha - hb <= PHASH_MAX_DISTANCE:
                        n_hits += 1
                        if len(examples) < 5:
                            examples.append((pa, pb))
                        break
            print(f"{b} images with a near-duplicate in {a}: {n_hits} / {len(ph[b])}")
            for pa, pb in examples:
                print(f"   e.g. {pa}  <->  {pb}")

    print("\nDone. Any non-zero 'shared' count means leakage: remove the duplicates "
          "from train (or val/test) and rerun your experiments.")


if __name__ == "__main__":
    main()
