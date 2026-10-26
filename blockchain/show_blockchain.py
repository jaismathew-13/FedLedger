"""Display real local blockchain deployment evidence without publishing a model."""
import json
from registry import connect, contract, DEPLOYMENT, log


def main():
    log('show_blockchain.py start: read-only live blockchain walkthrough.')
    client = connect()
    instance = contract(client)
    saved = json.loads(DEPLOYMENT.read_text(encoding='utf-8'))
    receipt = client.eth.get_transaction_receipt(saved['transaction_hash'])
    block = client.eth.get_block(receipt['blockNumber'])
    coordinator = instance.functions.coordinator().call()
    events = instance.events.ModelRegistered().get_logs(from_block=0, to_block='latest')
    print('\n=== LIVE LOCAL ETHEREUM BLOCKCHAIN ===')
    print(f'Node: {client.client_version}')
    print(f'Network: localhost only | chain ID {client.eth.chain_id}')
    print(f'Latest block: {client.eth.block_number}')
    print('Hardhat development state is in memory; redeploy after a node restart.')
    print('\n1. CONTRACT DEPLOYMENT TRANSACTION')
    print(f'Contract: {instance.address}')
    print(f'Transaction: {saved["transaction_hash"]}')
    print(f'Mined in block: {receipt["blockNumber"]}')
    print(f'Receipt status: {receipt["status"]} (1 = successful)')
    print(f'Gas used: {receipt["gasUsed"]} | development funds only')
    print(f'Block hash: {block["hash"].to_0x_hex()}')
    print(f'Parent block hash: {block["parentHash"].to_0x_hex()}')
    print('\n2. READ LIVE SMART-CONTRACT STATE')
    print(f'Coordinator: {coordinator}')
    print(f'Coordinator allowed to publish: {instance.functions.authorized(coordinator).call()}')
    print(f'Deployed code: {len(client.eth.get_code(instance.address))} bytes')
    print(f'Model registration events: {len(events)}')
    for event in events:
        values = event['args']
        print(f'  Round {values["round"]}, publisher {values["publisher"]}')
    print('\n3. HOW THE MODEL WILL USE THIS CHAIN')
    print('Train FedProx off-chain -> save best checkpoint -> SHA-256 checkpoint/manifest')
    print('-> authorized account registers hashes -> transaction is mined')
    print('-> verify local file hashes against the contract before using the model.')
    print('Images and model weights remain off-chain. Hash matching does not prove model quality.')
    if not events:
        print('\nWAITING FOR TRAINING: no model has been registered; no fake model was used.')
    log('show_blockchain.py completed: live deployment receipt, block and contract state displayed; no transactions submitted.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log(f'show_blockchain.py error: {type(exc).__name__}: {exc}')
        raise
