"""Create an off-chain manifest and exact SHA-256 arguments for ModelRegistry."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return '0x' + value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    required = ('best_model.pt', 'run_config.json', 'selection.json')
    for name in required:
        if not (args.run_dir / name).is_file():
            parser.error(f'Missing trained-run artifact: {name}')
    selection = json.loads((args.run_dir / 'selection.json').read_text(encoding='utf-8'))
    config = json.loads((args.run_dir / 'run_config.json').read_text(encoding='utf-8'))
    if config.get('algorithm') != 'FedProx' or int(selection['best_round']) < 1:
        parser.error('Expected a completed FedProx round selected on validation.')
    # Exclusive creation prevents silently replacing a previously prepared record.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        'schema': 'fedprox-model-registration-v1',
        'algorithm': 'FedProx',
        'selected_round': int(selection['best_round']),
        'selection_rule': config['selection_rule'],
        'files_sha256': {name: digest(args.run_dir / name) for name in required},
    }
    manifest_path = args.output_dir / 'manifest.json'
    manifest_path.write_bytes((json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode('utf-8'))
    manifest_hash = digest(manifest_path)
    # Run ID fingerprints run configuration bytes; independent of local folder name.
    arguments = {
        'runId': manifest['files_sha256']['run_config.json'],
        'round': manifest['selected_round'],
        'checkpointSha256': manifest['files_sha256']['best_model.pt'],
        'manifestSha256': manifest_hash,
    }
    (args.output_dir / 'registration.json').write_text(json.dumps(arguments, indent=2), encoding='utf-8')
    print(json.dumps(arguments, indent=2))


if __name__ == '__main__':
    main()
