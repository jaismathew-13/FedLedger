"""Separate local delegated-client contract; no historical FL contract changes."""
import json
from pathlib import Path
from web3 import Web3
from architecture_io import write_json
from blockchain.registry import connect, instance_id, receipt
from blockchain.hospital_directory import Directory

HERE = Path(__file__).resolve().parent
DEPLOYMENT = HERE/'deployment.client.local.json'


class ClientAuthorization:
    def __init__(self):
        self.client = connect()
        self.instance = instance_id(self.client)
        saved = json.loads(DEPLOYMENT.read_text())
        if saved['instance_id'] != self.instance:
            raise RuntimeError('Client authorization belongs to a different chain.')
        if Web3.keccak(self.client.eth.get_code(saved['address'])).to_0x_hex() != saved['runtime_code_hash']:
            raise RuntimeError('Client authorization contract code mismatch.')
        self.contract = self.client.eth.contract(address=saved['address'], abi=saved['abi'])

    def authorize(self, owner, delegate, consent_hash):
        return receipt(self.client, self.contract.functions.authorize(owner, delegate, consent_hash)
            .transact({'from': self.contract.functions.administrator().call()}))

    def eligible(self, owner, delegate):
        return self.contract.functions.eligible(owner, delegate).call()


def deploy():
    if DEPLOYMENT.exists():
        return ClientAuthorization().contract.address
    directory = Directory()
    client = directory.client
    artifact = json.loads((HERE/'artifacts/ClientAuthorization.json').read_text())
    factory = client.eth.contract(abi=artifact['abi'], bytecode=artifact['bytecode'])
    tx = factory.constructor(directory.contract.address).transact({'from': client.eth.accounts[0]})
    saved = receipt(client, tx)
    address = client.eth.get_transaction_receipt(tx)['contractAddress']
    saved.update(address=address, instance_id=instance_id(client), abi=artifact['abi'],
                 runtime_code_hash=Web3.keccak(client.eth.get_code(address)).to_0x_hex())
    write_json(DEPLOYMENT, saved)
    return address


if __name__ == '__main__':
    print(deploy())
