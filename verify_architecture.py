"""Verify a full-protocol best checkpoint against its on-chain global CID."""
import argparse
import json
from pathlib import Path
import tempfile

from architecture_io import LocalIPFS, sha256
from blockchain.protocol_chain import ProtocolChain
from train_fedprox import record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    reference = json.loads((args.run_dir/'best_global_reference.json').read_text())
    config = json.loads((args.run_dir/'run_config.json').read_text())
    identity = json.loads((args.run_dir/'run_identity.json').read_text())
    chain = ProtocolChain()
    if config['chain_instance_id'] != chain.instance or config['contract'] != chain.contract.address:
        raise RuntimeError('Run belongs to a different Hardhat instance/deployment; local receipts remain historical evidence only.')
    if sha256(args.run_dir/'run_config.json') != identity['run_id'] or identity['run_id'] != reference['run_id']:
        raise ValueError('Run configuration or identity differs from the bound registration.')
    model = chain.global_model(reference['run_id'], reference['selection_round'])
    if model['cid'] != reference['cid'] or model['sha256'] != reference['sha256']:
        raise ValueError('Saved best-model reference differs from the on-chain global record.')
    if sha256(args.run_dir/'best_model.pt') != model['sha256']:
        raise ValueError('Local best checkpoint digest does not match the blockchain.')
    with tempfile.TemporaryDirectory(dir=args.run_dir) as temporary:
        LocalIPFS().fetch(model['cid'], model['sha256'], Path(temporary)/'verified.pt')
    result = {'verified': True, 'run_id': reference['run_id'], 'selection_round': reference['selection_round'],
              'contract': chain.contract.address, 'cid': model['cid'], 'sha256': model['sha256']}
    print(json.dumps(result, indent=2))
    record(f'Full architecture checkpoint verified against on-chain CID and IPFS: {args.run_dir}')


if __name__ == '__main__':
    main()
