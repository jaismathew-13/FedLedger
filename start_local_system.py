"""Start local services; explicitly archive/redeploy after an ephemeral chain reset."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import hashlib
import uuid

from architecture_services import listening, start
from architecture_io import LocalIPFS
from blockchain.protocol_chain import ProtocolChain, deploy as deploy_protocol
from blockchain.hospital_directory import deploy as deploy_directory
from blockchain.client_authorization import deploy as deploy_client
from hospital_management import Management, now
from train_fedprox import record

ROOT = Path(__file__).resolve().parent


def finished_campaigns(management):
    """Use execution status, not the last UI command, to review migration safety."""
    with management.connection() as db:
        table=db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='campaigns'").fetchone()
        campaigns=list(db.execute('SELECT id,status,document FROM campaigns')) if table else []
    reviewed=[]
    for row in campaigns:
        uuid.UUID(row['id'])
        folder=management.state/'campaigns'/row['id']
        status_path=folder/'status.json'
        status=json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {'state':row['status']}
        state=status.get('state')
        if state not in ('completed','cancelled'):
            raise RuntimeError('Unfinished campaign '+row['id']+' ('+str(state)+') blocks automatic chain replacement. Its history is preserved; resolve it before restarting.')
        if state=='completed':
            document=json.loads(row['document'])
            history=folder/'execution/history.json'
            if (status.get('completed_round')!=document['rounds'] or status.get('error')
                    or not history.exists() or len(json.loads(history.read_text(encoding='utf-8')))!=document['rounds']):
                raise RuntimeError('Completed campaign evidence incomplete: '+row['id'])
        reviewed.append({'id':row['id'],'state':state,'folder':folder})
    return reviewed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh-chain', action='store_true',
                        help='Authorize archived replacement of a missing/restarted development chain.')
    args = parser.parse_args()
    management = Management()
    chain = None
    if listening(8545):
        try:
            chain = ProtocolChain()
        except Exception:
            if not args.fresh_chain:
                raise
    if chain is None:
        if not args.fresh_chain:
            raise RuntimeError('No matching chain is running. After reboot use --fresh-chain to archive old references and deploy a new development chain.')
        campaigns=finished_campaigns(management)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        archive = ROOT/'local_operations/chain_archives'/('restart_'+stamp)
        archive.mkdir(parents=True)
        with management.connection() as db:
            with closing(sqlite3.connect(archive/'organizations.sqlite3')) as backup:
                db.backup(backup)
        for file in (ROOT/'blockchain').glob('deployment*.json'):
            shutil.copy2(file, archive/file.name)
        for name in ('chain.stdout.log','chain.stderr.log','chain-process.json'):
            file=ROOT/'blockchain'/name
            if file.exists(): shutil.copy2(file,archive/name)
        migration_path=ROOT/'local_operations/chain_migration_current.json'
        if migration_path.exists(): shutil.copy2(migration_path,archive/migration_path.name)
        preserved=[]
        for campaign in campaigns:
            for file in campaign['folder'].rglob('*.json'):
                target=archive/'campaigns'/campaign['id']/file.relative_to(campaign['folder'])
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(file,target)
                preserved.append({'campaign':campaign['id'],'relative_path':file.relative_to(campaign['folder']).as_posix(),
                                  'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
        (archive/'historical_campaigns.json').write_text(json.dumps({'campaigns':[{'id':c['id'],'state':c['state']} for c in campaigns],
            'files':preserved,'notice':'Historical chain evidence; original models and datasets remain in place. New chain cannot verify old transactions.'},indent=2),encoding='utf-8')
        record('Explicit local restart: archived old chain references/database at '+str(archive))
        if not listening(8545): start('hardhat')
        # Only deployment pointers are replaced. Old receipts/models stay historical.
        for name in ('deployment.protocol.local.json','deployment.directory.local.json','deployment.client.local.json'):
            file=ROOT/'blockchain'/name
            if file.exists():
                if file.read_bytes() != (archive/name).read_bytes():
                    raise RuntimeError('Deployment changed during archive; refusing replacement.')
                file.unlink()
        deploy_protocol(); deploy_directory(); deploy_client()
        chain=ProtocolChain()
        with management.connection() as db:
            db.execute("UPDATE hospitals SET status=CASE WHEN status='approved' THEN 'pending' ELSE status END,receipt=NULL,heartbeat=NULL,readiness=NULL,updated=?",(now(),))
            db.execute('UPDATE portal_clients SET message=NULL,expires=0,consent=NULL,receipt=NULL')
            db.execute('DELETE FROM sessions');db.execute('DELETE FROM challenges')
            db.execute('DELETE FROM rosters')
            for campaign in campaigns:
                db.execute('UPDATE campaigns SET status=? WHERE id=?',(campaign['state'],campaign['id']))
            management.event(db,'local_administrator','new_chain_after_restart',None,
                             {'archive':str(archive),'instance':chain.instance,'reauthorization_required':True,
                              'historical_campaigns':[c['id'] for c in campaigns]})
        migration={'state':'complete','completed_utc':now(),'archive':str(archive),
                   'new_instance':chain.instance,'new_contract':chain.contract.address,
                   'historical_run':'run_20261020T093433_860908Z',
                   'historical_campaigns':[c['id'] for c in campaigns],
                   'notice':'Old transactions are historical. Hospitals require new approval and client delegation.'}
        migration_path.write_text(json.dumps(migration,indent=2),encoding='utf-8')
        (archive/'replacement.json').write_text(json.dumps(migration,indent=2),encoding='utf-8')
        record('New local chain deployed; registrations retained, approval/client authorization reset. No training started.')
        print('New development chain ready. Approve hospitals again and reauthorize their local clients.',flush=True)
    else:
        print('Matching Hardhat chain already running; no replacement.',flush=True)
    start('ipfs')
    LocalIPFS(progress_position=-1)
    print('Admin: http://127.0.0.1:8765/admin\nHospital: http://127.0.0.1:8765/hospital\nIPFS API: http://127.0.0.1:5002',flush=True)
    print('Training is launched separately from its campaign command.',flush=True)
    subprocess.run([sys.executable,str(ROOT/'start_project.py')],cwd=ROOT,check=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        record('Local system startup error: '+repr(exc))
        raise
