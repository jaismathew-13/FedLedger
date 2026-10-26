"""Local Hardhat adapter for the per-round hospital/peer protocol contract."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from progress_display import ProgressBar
from web3 import Web3
from blockchain.registry import connect, instance_id, receipt, sha, log, write_new

HERE = Path(__file__).resolve().parent
DEPLOYMENT = HERE / 'deployment.protocol.local.json'


class ProtocolChain:
    def __init__(self, hospital_accounts=None, hospital_signers=None):
        self.client = connect()
        self.instance = instance_id(self.client)
        if not DEPLOYMENT.exists():
            raise RuntimeError('Deploy the architecture contract with python -m blockchain.protocol_chain deploy.')
        self.saved = json.loads(DEPLOYMENT.read_text(encoding='utf-8'))
        if self.saved['instance_id'] != self.instance:
            raise RuntimeError('Hardhat restarted. Redeploy the protocol contract before starting a new run.')
        code = self.client.eth.get_code(self.saved['address'])
        if Web3.keccak(code).to_0x_hex() != self.saved['runtime_code_hash']:
            raise RuntimeError('Protocol registry code does not match its deployment record.')
        self.contract = self.client.eth.contract(address=self.saved['address'], abi=self.saved['abi'])
        self.coordinator = self.contract.functions.coordinator().call()
        accounts = self.client.eth.accounts
        if accounts[0] != self.coordinator or len(accounts) < 4:
            raise RuntimeError('Expected coordinator and three distinct unlocked local hospital accounts.')
        self.hospitals = hospital_accounts or accounts[1:4]
        self.hospital_signers = hospital_signers or {}
        if len(self.hospitals) != 3 or len(set(self.hospitals)) != 3:
            raise ValueError('Exactly three distinct hospital wallets required.')

    def guard(self):
        if instance_id(self.client) != self.instance:
            raise RuntimeError('Hardhat restarted during a run. Stop; do not silently continue on a new chain.')

    def transact(self, function, sender):
        self.guard()
        with ProgressBar(total=1, desc='Blockchain '+function.fn_name, unit='tx', position=0, disable=True, leave=False, dynamic_ncols=True) as bar:
            if sender in self.hospital_signers:
                account = self.hospital_signers[sender]
                transaction = function.build_transaction({'from': sender,
                    'nonce': self.client.eth.get_transaction_count(sender, 'pending'),
                    'chainId': self.client.eth.chain_id, 'gasPrice': self.client.eth.gas_price})
                signed = account.sign_transaction(transaction)
                result = receipt(self.client, self.client.eth.send_raw_transaction(signed.raw_transaction))
            else:
                result = receipt(self.client, function.transact({'from': sender}))
            bar.update(1)
            return result

    def open_run(self, run_id, policy_hash):
        return self.transact(self.contract.functions.openRun(run_id, policy_hash, self.hospitals), self.coordinator)

    def publish_global(self, run_id, round_number, model, evidence_hash):
        return self.transact(self.contract.functions.publishGlobal(run_id, round_number,
            model['cid'], model['sha256'], evidence_hash), self.coordinator)

    def global_model(self, run_id, round_number):
        self.guard()
        cid, digest, evidence, exists = self.contract.functions.getGlobal(run_id, round_number).call()
        if not exists:
            raise RuntimeError('No published global model for requested round.')
        return {'cid': cid, 'sha256': '0x' + bytes(digest).hex(), 'evidence_hash': '0x' + bytes(evidence).hex()}

    def submit_update(self, run_id, round_number, hospital, artifact, samples, parent_digest):
        return self.transact(self.contract.functions.submitUpdate(run_id, round_number, hospital,
            artifact['cid'], artifact['sha256'], samples, parent_digest), self.hospitals[hospital])

    def review(self, run_id, round_number, hospital, reviewer, valid, baseline, candidate, evidence_hash):
        return self.transact(self.contract.functions.submitReview(run_id, round_number, hospital,
            reviewer, valid, baseline, candidate, evidence_hash), self.hospitals[reviewer])

    def update(self, run_id, round_number, hospital):
        self.guard()
        value, accepted = self.contract.functions.getUpdate(run_id, round_number, hospital).call()
        return {'cid': value[0], 'sha256': '0x' + bytes(value[1]).hex(), 'samples': value[2],
                'parent_sha256': '0x' + bytes(value[3]).hex(), 'reviews': value[4],
                'approvals': value[5], 'exists': value[6], 'accepted': accepted}


def deploy():
    client = connect()
    current = instance_id(client)
    if DEPLOYMENT.exists():
        old = json.loads(DEPLOYMENT.read_text(encoding='utf-8'))
        if old['instance_id'] == current:
            return {'address': ProtocolChain().contract.address, 'existing': True}
        history = HERE / 'deployment-history'
        history.mkdir(exist_ok=True)
        DEPLOYMENT.rename(history / ('protocol_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ') + '.json'))
    artifact = json.loads((HERE / 'artifacts/FederatedProtocolRegistry.json').read_text(encoding='utf-8'))
    factory = client.eth.contract(abi=artifact['abi'], bytecode=artifact['bytecode'])
    tx = factory.constructor().transact({'from': client.eth.accounts[0]})
    result = receipt(client, tx)
    address = client.eth.get_transaction_receipt(tx)['contractAddress']
    result.update(address=address, chain_id=31337, instance_id=current,
        runtime_code_hash=Web3.keccak(client.eth.get_code(address)).to_0x_hex(), abi=artifact['abi'],
        artifact_sha256=sha(HERE / 'artifacts/FederatedProtocolRegistry.json'))
    write_new(DEPLOYMENT, result)
    log(f'Architecture protocol contract deployed: {address}')
    return {key: value for key, value in result.items() if key != 'abi'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('deploy', 'status'))
    args = parser.parse_args()
    try:
        if args.command == 'deploy':
            output = deploy()
        else:
            chain = ProtocolChain()
            output = {'address': chain.contract.address, 'instance_id': chain.instance,
                      'coordinator': chain.coordinator, 'hospitals': chain.hospitals, 'chain_id': 31337}
        print(json.dumps(output, indent=2))
    except Exception as exc:
        log(f'protocol_chain.py error: {type(exc).__name__}: {exc}')
        raise
