"""Prepare hospital manifests and inspect services; does not train or upload files."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from architecture_data import prepare_hospitals
from architecture_io import LocalIPFS, write_json, sha256
from blockchain.protocol_chain import ProtocolChain
from train_architecture import validate_policy
from train_fedprox import record

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, default=Path(r'D:\dataset_patientsplit'))
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    output = args.output_dir or ROOT/'architecture_preparation'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    output.mkdir(parents=True, exist_ok=False)
    record(f'Architecture preparation start: {output}; metadata/manifests only; no training, uploads or test-set access.')
    policy = json.loads((ROOT/'architecture_protocol.json').read_text())
    validate_policy(policy)
    ipfs, chain = LocalIPFS(), ProtocolChain()
    manifests, _ = prepare_hospitals(args.dataset_root, output, policy['seed'])
    import torch
    report = {'prepared_utc': datetime.now(timezone.utc).isoformat(),
        'policy_sha256': sha256(ROOT/'architecture_protocol.json'),
        'validation_manifest_sha256': [sha256(path) for path in manifests],
        'ipfs_endpoint': ipfs.endpoint,
        'ipfs_isolation': json.loads((ROOT/'.ipfs-local/offline-only.json').read_text()),
        'hardhat_chain_id': chain.client.eth.chain_id, 'hardhat_instance_id': chain.instance,
        'contract': chain.contract.address, 'hospital_accounts': chain.hospitals,
        'cuda_available': torch.cuda.is_available(),
        'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'free_disk_gib': shutil.disk_usage(ROOT).free / 1024 ** 3,
        'parallel_gpu_feasibility': 'not_exercised', 'training_executed': False,
        'test_evaluation_executed': False, 'end_to_end_tests_executed': False}
    write_json(output/'readiness.json', report)
    shutil.copyfile(ROOT/'architecture_protocol.json', output/'policy.json')
    print(json.dumps(report, indent=2))
    print(f'Hospital allocations: {output}/partition_summary.json')
    record(f'Architecture preparation completed: {output}; no data copying, training or upload.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        record(f'Architecture preparation failed: {type(exc).__name__}: {exc}')
        raise
