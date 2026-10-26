"""Deploy and use the model registry on the local development chain only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from web3 import Web3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RPC = 'http://127.0.0.1:8545'
DEPLOYMENT = HERE / 'deployment.hardhat.local.json'


def log(message):
    with (ROOT / 'RUN_LOG.md').open('a', encoding='utf-8') as stream:
        stream.write(f'\n{datetime.now(timezone.utc).isoformat()} {message}\n')


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return '0x' + value.hexdigest()


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def connect():
    client = Web3(Web3.HTTPProvider(RPC, request_kwargs={'timeout': 10}))
    if not client.is_connected():
        raise RuntimeError('Local chain unavailable. Start blockchain/start_chain.ps1 first.')
    if client.eth.chain_id != 31337 or 'hardhat' not in client.client_version.lower():
        raise RuntimeError('Expected local Hardhat development chain ID 31337.')
    return client


def contract(client):
    saved = json.loads(DEPLOYMENT.read_text(encoding='utf-8'))
    if saved.get('instance_id') != instance_id(client):
        raise RuntimeError('Hardhat node restarted. Run registry.py deploy to redeploy for this instance.')
    if saved['genesis_hash'] != client.eth.get_block(0)['hash'].to_0x_hex():
        raise RuntimeError('Chain was replaced; deployment belongs to another chain.')
    code = client.eth.get_code(saved['address'])
    if not code or Web3.keccak(code).to_0x_hex() != saved['runtime_code_hash']:
        raise RuntimeError('Deployed contract missing or bytecode differs from saved deployment.')
    return client.eth.contract(address=saved['address'], abi=saved['abi'])


def instance_id(client):
    response = client.provider.make_request('hardhat_metadata', [])
    if 'error' in response or not response.get('result', {}).get('instanceId'):
        raise RuntimeError('Hardhat node did not provide its instance identity.')
    return response['result']['instanceId']


def receipt(client, tx):
    log(f'Local transaction submitted: {tx.to_0x_hex()}')
    result = client.eth.wait_for_transaction_receipt(tx, timeout=60)
    if result['status'] != 1:
        raise RuntimeError(f'Transaction reverted: {tx.to_0x_hex()}')
    return {'transaction_hash': tx.to_0x_hex(), 'block_number': result['blockNumber'],
            'gas_used': result['gasUsed'], 'status': result['status']}


def registration_files(folder, run_folder):
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    args = json.loads((folder / 'registration.json').read_text(encoding='utf-8'))
    if manifest['schema'] != 'fedprox-model-registration-v1' or manifest['algorithm'] != 'FedProx':
        raise ValueError('Unsupported manifest schema or algorithm.')
    expected_names = {'best_model.pt', 'run_config.json', 'selection.json'}
    if set(manifest['files_sha256']) != expected_names:
        raise ValueError('Manifest must name exactly the three expected run artifacts.')
    for name in expected_names:
        if sha(run_folder / name) != manifest['files_sha256'][name]:
            raise ValueError(f'Artifact changed since preparation: {name}')
    expected = {'runId': sha(run_folder / 'run_config.json'),
                'round': manifest['selected_round'],
                'checkpointSha256': sha(run_folder / 'best_model.pt'),
                'manifestSha256': sha(folder / 'manifest.json')}
    if args != expected:
        raise ValueError('Registration arguments differ from local artifacts/manifest.')
    selection = json.loads((run_folder / 'selection.json').read_text(encoding='utf-8'))
    if args['round'] != selection['best_round']:
        raise ValueError('Selected round differs from selection.json.')
    return args


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    commands.add_parser('deploy')
    for name in ('register', 'verify'):
        sub = commands.add_parser(name)
        sub.add_argument('--registration-dir', type=Path, required=True)
        sub.add_argument('--run-dir', type=Path, required=True)
    authorize = commands.add_parser('authorize')
    authorize.add_argument('--address', required=True)
    authorize.add_argument('--revoke', action='store_true')
    args = parser.parse_args()
    log(f'registry.py command start: {sys.argv[1:]}')
    client = connect()
    if args.command == 'deploy':
        if DEPLOYMENT.exists():
            previous = json.loads(DEPLOYMENT.read_text(encoding='utf-8'))
            if previous.get('instance_id') != instance_id(client):
                history = HERE / 'deployment-history'
                history.mkdir(exist_ok=True)
                archived = history / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ') + '.json')
                DEPLOYMENT.rename(archived)
                log(f'Archived prior Hardhat instance deployment to {archived}; redeploying on new ephemeral instance.')
        if DEPLOYMENT.exists():
            # Idempotent: validate existing deployment rather than overwrite.
            instance = contract(client)
            result = {'address': instance.address, 'message': 'Existing deployment retained'}
        else:
            artifact = json.loads((HERE / 'artifacts/ModelRegistry.json').read_text(encoding='utf-8'))
            factory = client.eth.contract(abi=artifact['abi'], bytecode=artifact['bytecode'])
            tx = factory.constructor().transact({'from': client.eth.accounts[0]})
            result = receipt(client, tx)
            deployed = client.eth.get_transaction_receipt(tx)['contractAddress']
            result.update({'address': deployed, 'chain_id': 31337, 'rpc': RPC,
                'instance_id': instance_id(client),
                'genesis_hash': client.eth.get_block(0)['hash'].to_0x_hex(),
                'runtime_code_hash': Web3.keccak(client.eth.get_code(deployed)).to_0x_hex(),
                'abi': artifact['abi'], 'compiler': artifact['compiler'],
                'artifact_sha256': sha(HERE / 'artifacts/ModelRegistry.json')})
            write_new(DEPLOYMENT, result)
    elif args.command == 'status':
        result = {'connected': True, 'rpc': RPC, 'chain_id': client.eth.chain_id,
                  'block_number': client.eth.block_number, 'deployment_saved': DEPLOYMENT.exists()}
        if DEPLOYMENT.exists():
            instance = contract(client)
            events = instance.events.ModelRegistered().get_logs(from_block=0, to_block='latest')
            result.update(address=instance.address, instance_id=instance_id(client), coordinator=instance.functions.coordinator().call(),
                          registered_models=len(events))
    elif args.command == 'authorize':
        instance = contract(client)
        tx = instance.functions.setPublisher(Web3.to_checksum_address(args.address), not args.revoke).transact(
            {'from': client.eth.accounts[0]})
        result = receipt(client, tx)
    else:
        values = registration_files(args.registration_dir, args.run_dir)
        instance = contract(client)
        if args.command == 'register':
            receipt_path = args.registration_dir / 'transaction.local.json'
            if receipt_path.exists():
                raise FileExistsError('Registration receipt exists. Use verify instead of publishing again.')
            tx = instance.functions.registerModel(values['runId'], values['round'],
                values['checkpointSha256'], values['manifestSha256']).transact({'from': client.eth.accounts[0]})
            result = receipt(client, tx)
            result.update(contract=instance.address, chain_id=31337, instance_id=instance_id(client), **values)
            write_new(receipt_path, result)
        else:
            onchain = instance.functions.getModel(values['runId'], values['round']).call()
            if '0x' + bytes(onchain[0]).hex() != values['checkpointSha256'] or '0x' + bytes(onchain[1]).hex() != values['manifestSha256']:
                raise ValueError('Local artifacts do not match registered on-chain hashes.')
            result = {'verified': True, 'contract': instance.address, 'publisher': onchain[2],
                      'registered_at': onchain[3], **values}
    print(json.dumps(result, indent=2))
    log(f'registry.py {args.command} completed successfully.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log(f'registry.py error: {type(exc).__name__}: {exc}')
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
