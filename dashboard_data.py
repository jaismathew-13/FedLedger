"""Read-only dashboard views and explicit integrity checks for a saved run."""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile

from architecture_io import LocalIPFS, sha256
from blockchain.protocol_chain import ProtocolChain


def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def snapshot(run):
    config = read(run/'run_config.json')
    status = read(run/'execution.json', {})
    history_path = run/'history.csv'
    history = []
    if history_path.exists():
        for row in csv.DictReader(history_path.open(encoding='utf-8')):
            history.append({k: (v == 'True' if v in ('True', 'False') else float(v)) for k, v in row.items()})
    rounds = []
    for folder in sorted((run/'rounds').glob('round_*')):
        number = int(folder.name[6:])
        decisions = read(folder/'decisions.json', [])
        clients = []
        for hospital in range(3):
            local = run/'hospitals'/f'hospital_{hospital}'/folder.name
            update = read(local/'update.json')
            reviews = [read(path) for path in sorted((run/'hospitals').glob(f'hospital_*/{folder.name}/review_of_{hospital}.json'))]
            clients.append({'hospital': hospital, 'training': 'completed' if update else 'not completed',
                'local_model_saved': (local/'local_model.pt').is_file(), 'update': update,
                'submitted': (folder/f'update_{hospital}_receipt.json').is_file(),
                'reviews': reviews, 'decision': next((d for d in decisions if d['hospital_id'] == hospital), None),
                'error': read(local/'error.json'),
                'log': f'hospitals/hospital_{hospital}/{folder.name}/training.log'})
        rounds.append({'round': number, 'clients': clients, 'global': read(folder/'global.json'),
            'aggregation': read(folder/'aggregation.json'),
            'global_registered': (folder/'global_receipt.json').is_file()})
    accepted = sum(int(row['accepted_updates']) for row in history)
    return {'config': config, 'status': status, 'history': history, 'rounds': rounds,
        'accepted': accepted, 'rejected': sum(len(r['clients']) for r in rounds if r['aggregation']) - accepted,
        'selection': read(run/'selection.json', {}), 'validation': read(run/'validation_metrics.json', {}),
        'communication_overhead': None, 'comparison': 'No FedAvg results for this run; comparison unavailable.',
        'report_cid': None, 'report_note': 'Validation evidence committed by SHA-256, not uploaded as report CIDs.'}


def chain_status(run):
    try:
        chain = ProtocolChain()
        config = read(run/'run_config.json')
        historical = chain.instance != config['chain_instance_id'] or chain.contract.address != config['contract']
        return {'connected': True, 'network': 'Local Hardhat', 'chain_id': chain.client.eth.chain_id,
                'latest_block': chain.client.eth.block_number, 'contract': chain.contract.address,
                'historical_run': historical,
                'run_notice': 'Displayed experiment receipts belong to the previous chain and cannot be live-verified here.' if historical else 'Displayed experiment belongs to the current chain.',
                'checked_utc': datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {'connected': False, 'error': str(exc), 'checked_utc': datetime.now(timezone.utc).isoformat()}


def blocks(run, live=False):
    chain = None
    error = None
    if live:
        try:
            chain = ProtocolChain()
            if chain.instance != read(run/'run_config.json')['chain_instance_id']:
                raise RuntimeError('Chain instance differs from saved run.')
        except Exception as exc:
            error = str(exc)
            chain = None
    result = []
    for path in run.rglob('*receipt.json'):
        receipt = read(path)
        relative = path.relative_to(run)
        number = next((int(part[6:]) for part in relative.parts if part.startswith('round_')), 0)
        name = path.name
        hospital = None
        reviewer = None
        cid = None
        decision = None
        if name.startswith('update_'):
            hospital = int(name.split('_')[1])
            cid = (read(run/'hospitals'/f'hospital_{hospital}'/f'round_{number:04d}'/'update.json', {}) or {}).get('cid')
        elif name.startswith('review_'):
            parts = name.split('_')
            hospital, reviewer = int(parts[1]), int(parts[3])
        elif name in ('global_receipt.json', 'initial_global_receipt.json'):
            cid = (read(path.parent/('global.json' if number else 'initial_global.json'), {}) or {}).get('cid')
        if hospital is not None:
            decision = next((d for d in read(run/'rounds'/f'round_{number:04d}'/'decisions.json', []) if d['hospital_id'] == hospital), None)
        item = dict(receipt, event=path.stem.replace('_receipt', '').replace('_', ' '), round=number,
            hospital=hospital, reviewer=reviewer, cid=cid, decision=decision, report_cid=None,
            timestamp=None, source=relative.as_posix(), live_receipt_verified=False)
        if reviewer is not None:
            report_path = run/'hospitals'/f'hospital_{reviewer}'/f'round_{number:04d}'/f'review_of_{hospital}.json'
            item['peer_validation_report'] = read(report_path)
            item['validation_report_hash'] = sha256(report_path) if report_path.is_file() else None
            item['validation_report_storage'] = 'Local JSON; hash committed on-chain; no report CID recorded'
        if chain:
            try:
                current = chain.client.eth.get_transaction_receipt(receipt['transaction_hash'])
                block = chain.client.eth.get_block(current['blockNumber'])
                item.update(timestamp=datetime.fromtimestamp(block['timestamp'], timezone.utc).isoformat(),
                    live_receipt_verified=(current['blockNumber'] == receipt['block_number'] and current['status'] == receipt['status']),
                    block_hash=block['hash'].to_0x_hex(), parent_hash=block['parentHash'].to_0x_hex())
            except Exception as exc:
                item['live_error'] = str(exc)
        result.append(item)
    return {'blocks': sorted(result, key=lambda b: b['block_number']), 'live_error': error,
            'source': 'Saved receipts; live fields populated only when explicitly requested.'}


def audit(run, number, hospital):
    config = read(run/'run_config.json')
    identity = read(run/'run_identity.json')
    chain = ProtocolChain()
    if chain.instance != config['chain_instance_id'] or chain.contract.address != config['contract']:
        raise ValueError('Current blockchain does not match this run.')
    if sha256(run/'run_config.json') != identity['run_id']:
        raise ValueError('Run configuration hash mismatch.')
    folder = run/'rounds'/f'round_{number:04d}'
    local = run/'hospitals'/f'hospital_{hospital}'/folder.name
    stored = chain.update(identity['run_id'], number, hospital)
    global_model = chain.global_model(identity['run_id'], number)
    transport = LocalIPFS(progress_position=-1)
    checks = []
    with tempfile.TemporaryDirectory(dir=run) as temporary:
        for label, item, path in [('client', stored, local/'local_model.pt'),
                                  ('global', global_model, run/f'global_round_{number:04d}.pt')]:
            downloaded = transport.fetch(item['cid'], item['sha256'], Path(temporary)/(label+'.pt'))
            recalculated = sha256(downloaded)
            local_hash = sha256(path) if path.is_file() else None
            checks.append({'kind': label, 'cid': item['cid'], 'committed_hash': item['sha256'],
                'recalculated_ipfs_hash': recalculated, 'local_hash': local_hash,
                'verified': recalculated == item['sha256'] and local_hash == item['sha256']})
    reports = []
    for reviewer in range(3):
        if reviewer == hospital:
            continue
        path = run/'hospitals'/f'hospital_{reviewer}'/folder.name/f'review_of_{hospital}.json'
        committed = chain.contract.functions.getReview(identity['run_id'], number, hospital, reviewer).call()
        digest = '0x'+bytes(committed[3]).hex()
        actual = sha256(path) if path.is_file() else None
        reports.append({'reviewer': reviewer, 'submitted': committed[0], 'approved': committed[1],
            'report_cid': None, 'committed_hash': digest, 'recalculated_hash': actual,
            'verified': committed[0] and actual == digest, 'report': read(path)})
    aggregation_hash = sha256(folder/'aggregation.json')
    return {'round': number, 'hospital': hospital, 'accepted_on_chain': stored['accepted'],
        'models': checks, 'validation_reports': reports,
        'aggregation_evidence': {'committed_hash': global_model['evidence_hash'],
            'recalculated_hash': aggregation_hash, 'verified': aggregation_hash == global_model['evidence_hash']},
        'verified_utc': datetime.now(timezone.utc).isoformat()}
