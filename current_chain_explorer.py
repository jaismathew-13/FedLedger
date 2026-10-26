"""Bounded read-only explorer for the current local Hardhat chain."""
from datetime import datetime, timezone
import json
from pathlib import Path

from eth_utils import event_abi_to_log_topic
from web3._utils.events import get_event_data
from blockchain.registry import connect, instance_id

ROOT=Path(__file__).resolve().parent


def plain(value):
    if isinstance(value,bytes):return '0x'+value.hex()
    if isinstance(value,dict) or hasattr(value,'items'):return {str(k):plain(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [plain(v) for v in value]
    return value


def current_blocks(management,end=None,limit=25):
    if limit not in range(1,101):raise ValueError('Page size must be between 1 and 100 blocks.')
    client=connect();instance=instance_id(client);latest=client.eth.block_number
    end=latest if end is None else end
    if end not in range(latest+1):raise ValueError('Requested block is outside the current chain.')
    start=max(0,end-limit+1)
    with management.connection() as db:
        labels={r['wallet'].lower():r['code'] for r in db.execute('SELECT wallet,code FROM hospitals')}
        for row in db.execute('SELECT h.code,p.delegate FROM portal_clients p JOIN hospitals h ON h.id=p.hospital WHERE p.delegate IS NOT NULL'):
            labels[row['delegate'].lower()]=row['code']+' client'
    decoders={};contracts={}
    for name,label in [('protocol','Federated protocol'),('directory','Hospital directory'),('client','Client authorization')]:
        path=ROOT/'blockchain'/('deployment.'+name+'.local.json')
        if not path.exists():continue
        saved=json.loads(path.read_text(encoding='utf-8'))
        if saved.get('instance_id')!=instance:continue
        address=saved['address'].lower();contracts[address]=label
        for abi in saved['abi']:
            if abi['type']=='event':decoders[address,event_abi_to_log_topic(abi).hex()]=abi
    blocks=[]
    for number in range(start,end+1):
        block=client.eth.get_block(number,full_transactions=True);transactions=[]
        for tx in block['transactions']:
            receipt=client.eth.get_transaction_receipt(tx['hash']);events=[]
            for log in receipt['logs']:
                if not log['topics']:continue
                abi=decoders.get((log['address'].lower(),log['topics'][0].hex()))
                if not abi:continue
                decoded=get_event_data(client.codec,abi,log);args=plain(dict(decoded['args']))
                event=decoded['event'];title=event;category='training'
                if event=='MembershipChanged':
                    code=labels.get(args['wallet'].lower(),args['wallet'])
                    title=('Hospital approved: ' if args['authorized'] else 'Hospital deauthorized: ')+code;category='membership'
                elif event=='DelegateAuthorized':
                    code=labels.get(args['owner'].lower(),args['owner']);title='Client authorized: '+code;category='authorization'
                events.append({'event':event,'title':title,'category':category,'contract':log['address'],'arguments':args,'log_index':log['logIndex']})
            destination=tx.get('to');sender=tx['from'];created=receipt.get('contractAddress')
            transactions.append({'transaction_hash':tx['hash'].to_0x_hex(),'from':sender,'to':destination,
                                 'sender_label':labels.get(sender.lower()),
                                 'contract_name':contracts.get((destination or created or '').lower()),
                                 'created_contract':created,'status':receipt['status'],'gas_used':receipt['gasUsed'],
                                 'value_wei':int(tx['value']),'nonce':tx['nonce'],'events':events,
                                 'description':'Contract deployment' if not destination else 'Contract transaction' if tx.get('input',b'') not in (b'','0x') else 'Transfer'})
        blocks.append({'block_number':number,'block_hash':block['hash'].to_0x_hex(),'parent_hash':block['parentHash'].to_0x_hex(),
                       'timestamp':datetime.fromtimestamp(block['timestamp'],timezone.utc).isoformat(),
                       'transaction_count':len(transactions),'transactions':transactions})
    if instance_id(client)!=instance:raise RuntimeError('Chain changed during request; refresh to avoid mixing chain records.')
    return {'network':'Local Hardhat','chain_id':client.eth.chain_id,'instance_id':instance,'latest_block':latest,
            'start_block':start,'end_block':end,'page_size':limit,'older_end':start-1 if start>0 else None,
            'newer_end':min(latest,end+limit) if end<latest else None,'blocks':blocks,
            'checked_utc':datetime.now(timezone.utc).isoformat(),'source':'Current JSON-RPC block headers and receipts, not historical saved receipts.'}
