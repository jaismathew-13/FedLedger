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
from architecture_io import LocalIPFS, write_json
from blockchain.protocol_chain import ProtocolChain, deploy as deploy_protocol
from blockchain.hospital_directory import Directory, deploy as deploy_directory
from blockchain.client_authorization import ClientAuthorization, deploy as deploy_client
from blockchain.registry import connect, instance_id
from portal_workflow import Workflow
from hospital_management import Management, now
from train_fedprox import record, training_guard

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
        if state not in ('completed','cancelled','failed'):
            raise RuntimeError('Unfinished campaign '+row['id']+' ('+str(state)+') blocks automatic chain replacement. Its history is preserved; resolve it before restarting.')
        if state=='completed':
            document=json.loads(row['document'])
            history=folder/'execution/history.json'
            entries=json.loads(history.read_text(encoding='utf-8')) if history.exists() else []
            if (status.get('completed_round')!=document['rounds'] or status.get('error')
                    or [entry.get('round') for entry in entries]!=list(range(1,document['rounds']+1))):
                raise RuntimeError('Completed campaign evidence incomplete: '+row['id'])
        reviewed.append({'id':row['id'],'state':state,'folder':folder})
    return reviewed


def matching_contracts():
    chain = ProtocolChain()
    directory = Directory()
    delegation = ClientAuthorization()
    if directory.instance != chain.instance or delegation.instance != chain.instance:
        raise RuntimeError('Local contracts belong to different Hardhat instances.')
    if delegation.contract.functions.directory().call().lower() != directory.contract.address.lower():
        raise RuntimeError('Client authorization points to a different hospital directory.')
    return chain


def replace_chain(management):
    """Archive before replacement; retry partial deployment on the same instance."""
    Workflow(management)  # Initialize workflow tables even on a first-time installation.
    migration_path = management.state/'chain_migration_current.json'
    previous = json.loads(migration_path.read_text()) if migration_path.exists() else {}
    current = instance_id(connect()) if listening(8545) else None
    resume = previous.get('state') == 'in_progress' and current == previous.get('new_instance') and current is not None
    if resume:
        archive = Path(previous['archive']).resolve()
        base = (management.state/'chain_archives').resolve()
        if not archive.is_relative_to(base) or len(archive.relative_to(base).parts) != 1:
            raise RuntimeError('Invalid migration archive path.')
        for relative, expected in previous['archive_files'].items():
            source = archive/relative
            if not source.resolve().is_relative_to(archive) or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise RuntimeError('Migration backup changed; refusing recovery.')
        campaigns = finished_campaigns(management)
        if [{'id':c['id'],'state':c['state']} for c in campaigns] != previous.get('reviewed_campaigns',previous['historical_campaigns']):
            raise RuntimeError('Campaign history changed during interrupted migration.')
        migration = previous
        record('Resuming interrupted local chain migration from '+str(archive))
    else:
        campaigns=finished_campaigns(management)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        archive = management.state/'chain_archives'/('restart_'+stamp)
        archive.mkdir(parents=True)
        with management.connection() as db:
            with closing(sqlite3.connect(archive/'organizations.sqlite3')) as backup:
                db.backup(backup)
        for file in (ROOT/'blockchain').glob('deployment*.json'):
            shutil.copy2(file, archive/file.name)
        for name in ('chain.stdout.log','chain.stderr.log','chain-process.json'):
            file=ROOT/'blockchain'/name
            if file.exists(): shutil.copy2(file,archive/name)
        migration_path=management.state/'chain_migration_current.json'
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

        if not listening(8545):
            start('hardhat')
        current = instance_id(connect())
        migration = {'state':'in_progress','started_utc':now(),'archive':str(archive),
            'new_instance':current,'phase':'archived',
            'historical_campaigns':[{'id':c['id'],'state':c['state']} for c in campaigns],
            'reviewed_campaigns':[{'id':c['id'],'state':c['state']} for c in campaigns],
            'archive_files':{f.relative_to(archive).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
                             for f in archive.rglob('*') if f.is_file()}}
        write_json(migration_path,migration)
    try:
        # Old pointers are deleted only after their bytes are archived. New pointers
        # from a previous partial attempt are kept and validated by deploy().
        for name in ('deployment.protocol.local.json','deployment.directory.local.json','deployment.client.local.json'):
            file = ROOT/'blockchain'/name
            old = archive/name
            if file.exists():
                if old.exists() and file.read_bytes() == old.read_bytes():
                    file.unlink()
                elif not resume or json.loads(file.read_text()).get('instance_id') != current:
                    raise RuntimeError('Deployment changed during migration; refusing replacement.')
        for deploy in (deploy_protocol, deploy_directory, deploy_client):
            if instance_id(connect()) != current:
                raise RuntimeError('Hardhat changed during migration; stop and review before retrying.')
            deploy()
        chain = matching_contracts()
        if chain.instance != current or instance_id(connect()) != current:
            raise RuntimeError('Hardhat changed before enrollment reset.')
        migration.update(phase='deployments_verified',new_contract=chain.contract.address)
        write_json(migration_path,migration)
        with management.connection() as db:
            db.execute("UPDATE hospitals SET status=CASE WHEN status='approved' THEN 'pending' ELSE status END,receipt=NULL,heartbeat=NULL,readiness=NULL,updated=?",(now(),))
            db.execute('UPDATE portal_clients SET message=NULL,expires=0,consent=NULL,receipt=NULL')
            db.execute('DELETE FROM sessions'); db.execute('DELETE FROM challenges'); db.execute('DELETE FROM rosters')
            for campaign in campaigns:
                db.execute('UPDATE campaigns SET status=? WHERE id=?',(campaign['state'],campaign['id']))
            management.event(db,'local_administrator','new_chain_after_restart',None,
                {'archive':str(archive),'instance':chain.instance,'reauthorization_required':True,
                 'historical_campaigns':[c['id'] for c in campaigns]})
        migration.update(state='complete',phase='complete',completed_utc=now(),last_error=None,
            historical_run='run_20261020T093433_860908Z',historical_campaigns=[c['id'] for c in campaigns],
            notice='Old transactions are historical. Hospitals require new approval and client delegation.')
        write_json(archive/'replacement.json',migration)
        write_json(migration_path,migration)
        record('New local chain ready; old evidence retained, including failed campaigns. No training started.')
        print('New development chain ready. Approve hospitals again and reauthorize their local clients.',flush=True)
        return chain
    except BaseException as exc:
        migration.update(state='in_progress',last_error=type(exc).__name__+': '+str(exc))
        write_json(migration_path,migration)
        record('Local chain migration interrupted; rerun --fresh-chain to resume on this instance: '+type(exc).__name__)
        raise


def ensure_chain(management, fresh=False):
    migration_path=management.state/'chain_migration_current.json'
    migration=json.loads(migration_path.read_text()) if migration_path.exists() else {}
    if listening(8545):
        connect()  # Fail closed on another RPC service; --fresh-chain is not an override.
        if migration.get('state') != 'in_progress':
            try:
                chain=matching_contracts()
            except Exception:
                if not fresh:
                    raise
            else:
                print('Matching Hardhat contracts already running; no replacement.',flush=True)
                return chain
    if not fresh:
        raise RuntimeError('No matching complete chain is running. Use --fresh-chain to archive/redeploy or resume an interrupted migration.')
    # Excludes training and competing migrations while references/approvals change.
    with training_guard():
        # Another startup may have completed after our first inspection.
        latest=json.loads(migration_path.read_text()) if migration_path.exists() else {}
        if listening(8545) and latest.get('state') != 'in_progress':
            connect()
            try:
                return matching_contracts()
            except Exception:
                pass
        return replace_chain(management)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh-chain', action='store_true',
                        help='Authorize archived replacement or recovery of a development chain.')
    args = parser.parse_args()
    management = Management()
    ensure_chain(management,args.fresh_chain)
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
