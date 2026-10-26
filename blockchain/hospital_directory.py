"""Separate local directory deployment; never replaces the FL contract."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from web3 import Web3
from blockchain.registry import connect, instance_id, receipt, sha
from architecture_io import write_json

HERE = Path(__file__).resolve().parent
DEPLOYMENT = HERE/'deployment.directory.local.json'


class Directory:
    def __init__(self):
        self.client = connect()
        self.instance = instance_id(self.client)
        saved = json.loads(DEPLOYMENT.read_text())
        if saved['instance_id'] != self.instance:
            raise RuntimeError('Hospital directory belongs to another chain; no automatic redeployment.')
        if Web3.keccak(self.client.eth.get_code(saved['address'])).to_0x_hex() != saved['runtime_code_hash']:
            raise RuntimeError('Hospital directory code differs from its deployment.')
        self.contract = self.client.eth.contract(address=saved['address'], abi=saved['abi'])

    def membership(self, wallet):
        identity, authorized, revision = self.contract.functions.memberships(wallet).call()
        return {'organization_hash': '0x'+bytes(identity).hex(), 'authorized': authorized, 'revision': revision}

    def set(self, wallet, identity, authorized):
        if instance_id(self.client) != self.instance:
            raise RuntimeError('Chain changed; refusing enrollment.')
        function = self.contract.functions.setMembership(wallet, identity, authorized)
        return receipt(self.client, function.transact({'from': self.contract.functions.administrator().call()}))


def deploy():
    if DEPLOYMENT.exists():
        return {'existing': True, 'address': Directory().contract.address}
    client = connect()
    artifact = json.loads((HERE/'artifacts/HospitalDirectory.json').read_text())
    factory = client.eth.contract(abi=artifact['abi'], bytecode=artifact['bytecode'])
    transaction = factory.constructor().transact({'from': client.eth.accounts[0]})
    saved = receipt(client, transaction)
    address = client.eth.get_transaction_receipt(transaction)['contractAddress']
    saved.update(address=address, instance_id=instance_id(client), chain_id=client.eth.chain_id,
        abi=artifact['abi'], runtime_code_hash=Web3.keccak(client.eth.get_code(address)).to_0x_hex(),
        artifact_sha256=sha(HERE/'artifacts/HospitalDirectory.json'),
        created_utc=datetime.now(timezone.utc).isoformat())
    write_json(DEPLOYMENT, saved)
    return {'existing': False, 'address': address}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['deploy', 'status'])
    args = parser.parse_args()
    print(json.dumps(deploy() if args.command == 'deploy' else {'address': Directory().contract.address}, indent=2))
