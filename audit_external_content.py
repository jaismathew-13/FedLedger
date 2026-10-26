"""Read-only perceptual comparison; similarity flags are not patient identity proof."""
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image, ImageOps, ImageDraw

from train_fedprox import record

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'multiseed_outputs'/'external_content_audit'
SOURCE = ROOT/'Chest-X-Ray Epic Hospital Chittagong, Bangladesh pneumonia'
RUN = ROOT/'architecture_outputs'/'run_20261020T093433_860908Z'


def fingerprint(path):
    with Image.open(path) as image:
        return str(path), int(str(imagehash.phash(image.convert('L'))), 16)


def thumbnail(path):
    with Image.open(path) as image:
        return np.asarray(image.convert('L').resize((128, 128)), dtype=np.float32) / 255


def main():
    OUT.mkdir(exist_ok=True)
    record('Command start: audit_external_content.py; unchanged images, no training/evaluation; pHash screening distance<=6, correlation/MAE supplemental, visual review needed.')
    used = set()
    for manifest in (RUN/'hospitals').glob('hospital_*/data_manifest.json'):
        data = json.loads(manifest.read_text())
        used.update(path for key in ('train', 'val') for path, _ in data[key])
    cache = json.loads((ROOT/'multiseed_outputs/data_review/phash_cache.json').read_text())
    reference = []
    missing = []
    for path in sorted(used):
        stat = Path(path).stat()
        saved = cache.get(path)
        if saved and saved['stamp'] == [stat.st_size, stat.st_mtime_ns]:
            reference.append((path, int(saved['hash'], 16)))
        else:
            missing.append(Path(path))
    candidates = sorted(p for p in SOURCE.rglob('*') if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp') and p.is_file())
    with ThreadPoolExecutor(max_workers=4) as pool:
        reference.extend(pool.map(fingerprint, missing))
        external = list(pool.map(fingerprint, candidates))
    print(f'Comparing {len(external)} external images against {len(reference)} used images', flush=True)
    rows = []
    for path, value in external:
        nearest_path, nearest_value = min(reference, key=lambda item: (value ^ item[1]).bit_count())
        distance = (value ^ nearest_value).bit_count()
        row = {'external': path, 'split': Path(path).relative_to(SOURCE).parts[0],
            'reference': nearest_path, 'phash_distance': distance, 'similarity_flag': distance <= 6}
        if distance <= 6:
            left, right = thumbnail(path), thumbnail(nearest_path)
            row['resized_pixel_correlation'] = float(np.corrcoef(left.flatten(), right.flatten())[0, 1])
            row['resized_pixel_mae'] = float(np.mean(np.abs(left-right)))
        else:
            row.update(resized_pixel_correlation=None, resized_pixel_mae=None)
        rows.append(row)
    with (OUT/'nearest_matches.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    report = {'images': len(rows), 'reference_images': len(reference),
        'method': '64-bit pHash nearest neighbour; <=6 is a screening flag, not a confirmed duplicate',
        'per_split': {split: {'images': sum(r['split'] == split for r in rows),
            'distance_zero': sum(r['split'] == split and r['phash_distance'] == 0 for r in rows),
            'distance_at_most_2': sum(r['split'] == split and r['phash_distance'] <= 2 for r in rows),
            'flags_at_most_6': sum(r['split'] == split and r['phash_distance'] <= 6 for r in rows)}
            for split in sorted({r['split'] for r in rows})},
        'source_documentation': 'https://data.mendeley.com/datasets/wndbd5r26y/4',
        'provenance_note': 'Repository describes Epic Chittagong primary data; description does not supply patient mapping and local counts differ. Local version/copy provenance unconfirmed.',
        'limitations': 'Similar chest radiographs can share pHashes. Cropped/rotated/edited copies may evade screening. No match does not establish patient independence.'}
    (OUT/'summary.json').write_text(json.dumps(report, indent=2))
    # Strongest candidates for visual inspection; no source file changes.
    flagged = sorted((r for r in rows if r['similarity_flag']), key=lambda r: (r['phash_distance'], r['resized_pixel_mae']))[:8]
    if flagged:
        sheet = Image.new('RGB', (900, len(flagged)*300), 'white')
        draw = ImageDraw.Draw(sheet)
        for i, row in enumerate(flagged):
            for j, key in enumerate(('external', 'reference')):
                with Image.open(row[key]) as image:
                    fitted = ImageOps.contain(image.convert('RGB'), (430, 255))
                    sheet.paste(fitted, (j*450, i*300+35))
                draw.text((j*450+5, i*300+3), key+': '+Path(row[key]).name[:50], fill='black')
            draw.text((5, i*300+18), f"pHash={row['phash_distance']} corr={row['resized_pixel_correlation']:.5f} MAE={row['resized_pixel_mae']:.5f}", fill='black')
        sheet.save(OUT/'strongest_matches.jpg')
    print(json.dumps(report, indent=2), flush=True)
    record(f'Content audit completed: {OUT}; similarity flags retained for review; no source files changed.')


if __name__ == '__main__':
    main()
