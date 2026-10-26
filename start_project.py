"""Start the existing run's local interface without replacing its blockchain."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from architecture_services import start, listening
from architecture_io import LocalIPFS
from blockchain.protocol_chain import ProtocolChain
from train_fedprox import record

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=ROOT/'architecture_outputs/run_20261020T093433_860908Z')
    args = parser.parse_args()
    config = json.loads((args.run_dir/'run_config.json').read_text())
    record(f'Project startup command: run={args.run_dir}; existing chain required; no deployment/training.')
    if not listening(8545):
        raise RuntimeError('The original Hardhat node is unavailable. Starting a fresh node cannot restore this run. '
                           'Saved receipts remain historical evidence. Do not redeploy over the recorded deployment.')
    chain = ProtocolChain()
    if chain.instance != config['chain_instance_id'] or chain.contract.address != config['contract']:
        migration_path = ROOT/'local_operations/chain_migration_current.json'
        migration = json.loads(migration_path.read_text()) if migration_path.exists() else {}
        if (migration.get('state') != 'complete'
                or migration.get('new_instance') != chain.instance
                or migration.get('new_contract') != chain.contract.address
                or migration.get('historical_run') != args.run_dir.name):
            raise RuntimeError('Existing node differs from this run and has no matching authorized migration.')
        print('Authorized new chain active. Displayed experiment receipts remain historical evidence.')
    start('ipfs')
    LocalIPFS(progress_position=-1)
    if listening(8765):
        import requests
        session = requests.Session(); session.trust_env = False
        from hospital_management import STATE
        session.headers['Authorization'] = 'Bearer '+(STATE/'admin.key').read_text(encoding='utf-8').strip()
        response = session.get('http://127.0.0.1:8765/api/model', timeout=10)
        response.raise_for_status()
        expected = json.loads((args.run_dir/'run_identity.json').read_text())['run_id']
        if response.json()['provenance']['run_id'] != expected:
            raise RuntimeError('Dashboard port belongs to another run. No duplicate launched.')
        print('Project already running: http://127.0.0.1:8765')
    else:
        subprocess.run([sys.executable, '-u', str(ROOT/'project_dashboard.py'),
                        '--run-dir', str(args.run_dir.resolve())], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
