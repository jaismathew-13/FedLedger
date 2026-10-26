"""Expose existing architecture CIDs in IPFS Desktop's named Files view."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from architecture_io import LocalIPFS, write_json
from train_fedprox import record
from progress_display import ProgressBar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if not (run / 'run_config.json').is_file():
        raise ValueError('Expected an architecture run directory.')
    ipfs = LocalIPFS(progress_position=-1)
    base = '/training/' + run.name
    entries = []
    def add(metadata, target):
        value = json.loads(metadata.read_text())
        ipfs.validate_cid(value['cid'])
        entries.append({'cid': value['cid'], 'sha256': value['sha256'], 'mfs_path': base + '/' + target})
    add(run / 'initial_global.json', 'initial_global.pt')
    for metadata in sorted((run / 'rounds').glob('round_*/global.json')):
        round_name = metadata.parent.name
        add(metadata, round_name + '/global.pt')
        for hospital in range(3):
            update = run / 'hospitals' / f'hospital_{hospital}' / round_name / 'update.json'
            if update.is_file():
                add(update, round_name + f'/hospital_{hospital + 1}.pt')
    if (run / 'best_global_reference.json').is_file():
        add(run / 'best_global_reference.json', 'best_model.pt')
    if entries:
        globals_metadata = sorted((run / 'rounds').glob('round_*/global.json'))
        if globals_metadata:
            add(globals_metadata[-1], 'latest_model.pt')
    report = {'run_dir': str(run), 'mfs_root': base, 'verified': []}
    record(f'Command start: show_training_files.py --run-dir {run}; expose existing CIDs in local MFS, no model uploads.')
    try:
        for entry in ProgressBar(entries, desc='Add Desktop file references', unit='file'):
            target = entry['mfs_path']
            ipfs.post('files/mkdir', params={'arg': target.rsplit('/', 1)[0], 'parents': 'true'})
            response = ipfs.session.post(ipfs.endpoint + 'files/stat', params={'arg': target}, timeout=(10, 30))
            if response.ok:
                if response.json()['Hash'] != entry['cid']:
                    raise RuntimeError(f'Refusing to overwrite different existing MFS file: {target}')
            else:
                # Confirm existence through directory listing; other stat errors must not be hidden.
                listing = ipfs.post('files/ls', params={'arg': target.rsplit('/', 1)[0]}).json()
                if any(item['Name'] == target.rsplit('/', 1)[1] for item in (listing.get('Entries') or [])):
                    response.raise_for_status()
                ipfs.post('files/cp', params=[('arg', '/ipfs/' + entry['cid']), ('arg', target)])
            actual = ipfs.post('files/stat', params={'arg': target}).json()
            if actual['Hash'] != entry['cid']:
                raise RuntimeError(f'MFS CID mismatch: {target}')
            report['verified'].append(dict(entry, bytes=actual['Size']))
        ipfs.post('files/flush', params={'arg': base})
        report['completed'] = True
        print(f'Visible in IPFS Desktop: Files > training > {run.name}')
    finally:
        write_json(run / 'ipfs_desktop_files.json', report)
        record(f'Desktop references command ended: verified={len(report["verified"])}; completed={report.get("completed", False)}; report={run / "ipfs_desktop_files.json"}')


if __name__ == '__main__':
    main()
