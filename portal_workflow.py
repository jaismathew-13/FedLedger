"""Role-scoped local client data, future rounds and operational controls."""
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import threading
import time
import uuid

from eth_account import Account
from eth_account.messages import encode_defunct

from architecture_io import LocalIPFS, sha256, write_json, read_json
from blockchain.client_authorization import ClientAuthorization
from blockchain.hospital_directory import Directory
from hospital_management import Management, now
from patient_split_check import patient_id, IMAGE_EXTENSIONS


class Workflow:
    def __init__(self, management):
        self.management = management
        self.state = management.state
        self.workspace_lock = threading.RLock()
        with management.connection() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS portal_clients (
                hospital TEXT PRIMARY KEY, delegate TEXT, message TEXT, expires REAL,
                consent TEXT, receipt TEXT, manifest TEXT, summary TEXT);
              CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY, created TEXT, document TEXT, status TEXT, control TEXT);
              CREATE TABLE IF NOT EXISTS participation (
                campaign TEXT, hospital TEXT, joined INTEGER, updated TEXT,
                PRIMARY KEY(campaign,hospital));
              CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT, campaign TEXT, hospital TEXT,
                created TEXT, message TEXT);
            ''')
            columns={row[1] for row in db.execute('PRAGMA table_info(portal_clients)')}
            if 'sync_utc' not in columns: db.execute('ALTER TABLE portal_clients ADD COLUMN sync_utc TEXT')

    def owner(self, token, require_approved=True):
        profile = self.management.me(token)
        row = profile['application']
        if not row or (require_approved and (row['status'] != 'approved' or not Directory().membership(row['wallet'])['authorized'])):
            raise PermissionError('Approved hospital wallet required.')
        return row

    def folder(self, identity):
        # Resolve the immutable organization code from its database identity.
        uuid.UUID(identity)
        with self.management.connection() as db:
            row = db.execute('SELECT code FROM hospitals WHERE id=?', (identity,)).fetchone()
        if not row:
            raise ValueError('Hospital not found.')
        code = row['code']
        if not re.fullmatch(r'[A-Z0-9_-]{3,32}', code) or re.fullmatch(r'CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9]', code):
            raise ValueError('Hospital code cannot be used as a Windows workspace name.')
        base = (self.state/'hospital_data').resolve()
        root = base/code
        if root.resolve() != root:
            raise PermissionError('Hospital workspace must not alias another folder.')
        return root

    def prepare_workspace(self, identity):
        """Copy a legacy workspace once; frozen manifests retain their old paths."""
        with self.workspace_lock:
            root = self.folder(identity)
            legacy = (self.state/'hospital_data'/identity).absolute()
            if not root.exists() and legacy.exists():
                if legacy.resolve() != legacy or any(not p.resolve().is_relative_to(legacy) for p in legacy.rglob('*')):
                    raise PermissionError('Legacy workspace contains a junction or symlink outside its hospital folder.')
                temporary = root.with_name('.'+root.name+'-'+uuid.uuid4().hex+'.copying')
                shutil.copytree(legacy, temporary)
                temporary.rename(root)
                with (Path(__file__).parent/'RUN_LOG.md').open('a', encoding='utf-8') as stream:
                    stream.write(f'\n{now()} Copied hospital workspace {legacy} to {root}; original files and registered manifests preserved.\n')
            for split in ('train', 'val'):
                for label in ('NORMAL', 'PNEUMONIA'):
                    (root/split/label).mkdir(parents=True, exist_ok=True)
            return root

    def prepare_agent(self, token):
        row = self.owner(token)
        folder = self.state/'agents'/row['id']
        folder.mkdir(parents=True, exist_ok=True)
        key = folder/'client.key'
        if not key.exists():
            account = Account.create()
            with key.open('x', encoding='utf-8') as stream:
                stream.write(account.key.hex())
        account = Account.from_key(key.read_text())
        message = ('Fed-Ledger local training client authorization\n'
            f'Owner: {row["wallet"]}\nOrganization: {row["id"]}\nDelegate: {account.address}\n'
            f'Origin: http://127.0.0.1:8765\nNonce: {secrets.token_hex(32)}\n'
            'Authorize this development client to submit model updates for future local runs. '
            'No authority over funds or patient records. Expires in 5 minutes.')
        with self.management.connection() as db:
            db.execute('INSERT OR IGNORE INTO portal_clients(hospital) VALUES(?)', (row['id'],))
            db.execute('UPDATE portal_clients SET delegate=?,message=?,expires=? WHERE hospital=?',
                       (account.address, message, time.time()+300, row['id']))
        root = self.prepare_workspace(row['id'])
        return {'delegate': account.address, 'message': message, 'data_folder': str(root.resolve())}

    def authorize_agent(self, token, payload):
        row = self.owner(token)
        with self.management.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            client = db.execute('SELECT * FROM portal_clients WHERE hospital=?', (row['id'],)).fetchone()
            if not client or not client['message'] or client['expires'] < time.time():
                raise ValueError('Request a fresh client authorization challenge.')
            signature = payload['signature']
            signer = Account.recover_message(encode_defunct(text=client['message']), signature=signature)
            if signer != row['wallet']:
                raise PermissionError('Client delegation must be signed by the hospital owner.')
            digest = '0x'+hashlib.sha256(client['message'].encode()).hexdigest()
            receipt = ClientAuthorization().authorize(row['wallet'], client['delegate'], digest)
            consent = {'message': client['message'], 'signature': signature, 'sha256': digest}
            db.execute('UPDATE portal_clients SET message=NULL,expires=0,consent=?,receipt=? WHERE hospital=?',
                       (json.dumps(consent), json.dumps(receipt), row['id']))
            self.management.event(db, row['wallet'], 'training_delegate_authorized', row['id'],
                                  {'delegate': client['delegate'], 'receipt': receipt})
        return {'delegate': client['delegate'], 'receipt': receipt}

    def configure(self, token, payload):
        row = self.owner(token)
        base=(self.state/'hospital_data').resolve()
        root = self.folder(row['id']).resolve()
        if not root.is_relative_to(base) or root.relative_to(base).parts!=(row['code'],):
            raise PermissionError('Hospital root must not alias another folder through a junction or symlink.')
        namespace = str(payload.get('patient_namespace', '')).strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{3,80}', namespace):
            raise ValueError('Supply a documented patient-ID namespace (3ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ80 letters/digits/_/-).')
        mapping = {}
        map_path = root/'patients.csv'
        if map_path.exists():
            if not map_path.resolve().is_relative_to(root): raise PermissionError('Patient map outside owning data folder.')
            with map_path.open(encoding='utf-8-sig', newline='') as stream:
                for item in csv.DictReader(stream):
                    relative = item['relative_path'].replace('\\', '/')
                    if relative in mapping or not item['patient_id'].strip():
                        raise ValueError('Patient mapping contains duplicate paths or blank patient IDs.')
                    mapping[relative] = item['patient_id'].strip()
        data = {'train': [], 'val': [], 'fingerprints': {}, 'patients': {}, 'namespace': namespace}
        seen = set()
        ids = {'train': set(), 'val': set()}
        counts = {}
        for split in ('train', 'val'):
            for label, number in (('NORMAL', 0), ('PNEUMONIA', 1)):
                folder = root/split/label
                files = sorted(path for path in folder.rglob('*') if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
                if not files:
                    raise ValueError(f'Both classes required in {split}; no images found in {label}.')
                counts[split+'/'+label] = len(files)
                for path in files:
                    resolved = path.resolve()
                    if not resolved.is_relative_to(root):
                        raise PermissionError('Symlink/junction escapes the owning hospital data folder.')
                    relative = resolved.relative_to(root).as_posix()
                    identity, parsed = patient_id(resolved, split, root)
                    identity = mapping.get(relative) or (identity if parsed else None)
                    if not identity:
                        raise ValueError('Patient ID missing: supply patients.csv with relative_path,patient_id for all unparsed names.')
                    identity = namespace+':'+identity
                    digest = sha256(resolved)
                    if digest in seen:
                        raise ValueError('Duplicate image bytes in local data; original files left unchanged.')
                    seen.add(digest); ids[split].add(identity)
                    data[split].append([str(resolved), number])
                    data['fingerprints'][str(resolved)] = digest
                    data['patients'][str(resolved)] = identity
        if ids['train'] & ids['val']:
            raise ValueError('A patient appears in both train and val; fix the split using copies, not original-file changes.')
        with self.management.connection() as db:
            # Prevent local configurations from silently sharing raw examples or patients.
            for other in db.execute('SELECT hospital,manifest FROM portal_clients WHERE hospital!=? AND manifest IS NOT NULL', (row['id'],)):
                saved = json.loads(Path(other['manifest']).read_text())
                if seen & set(saved['fingerprints'].values()):
                    raise ValueError('Exact image overlap with another configured hospital; configuration refused.')
                if set(data['patients'].values()) & set(saved['patients'].values()):
                    raise ValueError('Shared patient IDs within the same namespace across hospitals; configuration refused.')
            db.execute('INSERT OR IGNORE INTO portal_clients(hospital) VALUES(?)', (row['id'],))
            version = str(uuid.uuid4())
            manifest = self.state/'private_manifests'/row['id']/(version+'.json')
            write_json(manifest, data)
            summary = {'version': version, 'class_counts': counts, 'train_images': len(data['train']),
                'val_images': len(data['val']), 'train_patients': len(ids['train']), 'val_patients': len(ids['val']),
                'manifest_sha256': sha256(manifest), 'configured_utc': now(),
                'note': 'Exact-byte and mapped/inferred-ID checks only; perceptual/source independence still requires review.'}
            db.execute('UPDATE portal_clients SET manifest=?,summary=? WHERE hospital=?',
                       (str(manifest), json.dumps(summary), row['id']))
            self.management.event(db, row['wallet'], 'local_data_configured', row['id'], summary)
        return {'summary': summary, 'data_folder': str(root)}

    def configurations(self):
        policy = json.loads((Path(__file__).parent/'architecture_protocol.json').read_text())
        return [{'id': 'registered_fedprox_v1', 'algorithm': 'FedProx', 'local_epochs': policy['local_epochs'],
                 'mu': policy['mu'], 'seed': policy['seed'], 'max_rounds': policy['rounds'],
                 'acceptance': policy['peer_validation'], 'aggregation': policy['aggregation']}]

    def create(self, token, payload):
        self.management.admin(token)
        identities = payload.get('hospital_ids', [])
        rounds = payload.get('rounds')
        if not isinstance(identities, list) or len(identities) != 3 or len(set(identities)) != 3:
            raise ValueError('Exactly three distinct approved hospitals required by this protocol.')
        if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds not in range(1, 21):
            raise ValueError('Round count must be 1ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ20, registered before this new campaign starts.')
        if payload.get('configuration') != 'registered_fedprox_v1':
            raise ValueError('Select an approved configuration; arbitrary parameters are not accepted.')
        participants = []
        delegation = ClientAuthorization()
        with self.management.connection() as db:
            for identity in identities:
                hospital = db.execute('SELECT * FROM hospitals WHERE id=?', (identity,)).fetchone()
                client = db.execute('SELECT * FROM portal_clients WHERE hospital=?', (identity,)).fetchone()
                if not hospital or hospital['status'] != 'approved' or not client or not client['manifest'] or not client['consent']:
                    raise ValueError('Each hospital needs approval, local data configuration and signed client delegation.')
                if not delegation.eligible(hospital['wallet'], client['delegate']):
                    raise ValueError('Client delegation is not currently authorized on-chain.')
                summary = json.loads(client['summary'])
                participants.append({'id': identity, 'code': hospital['code'], 'owner': hospital['wallet'],
                    'delegate': client['delegate'], 'manifest_sha256': summary['manifest_sha256'],
                    'data_version': summary['version']})
            identity = str(uuid.uuid4())
            config = self.configurations()[0]
            document = {'id': identity, 'created_utc': now(), 'rounds': rounds, 'configuration': config,
                'participants': participants, 'timeout_seconds': 3600,
                'source_sha256':{name:sha256(Path(__file__).parent/name) for name in ('fedprox_core.py','portal_workers.py','round_coordinator.py','peer_policy.py','blockchain/protocol_chain.py')},
                'initial_model': 'original_pretrained_global_round_0000', 'aggregation_gate': True,
                'privacy_scope': 'local single-machine worker simulation; application roles restrict raw-data views, not OS isolation'}
            db.execute('INSERT INTO campaigns VALUES(?,?,?,?,?)',
                       (identity, now(), json.dumps(document), 'created', 'pause'))
            for item in participants:
                db.execute('INSERT INTO participation VALUES(?,?,?,?)', (identity, item['id'], 0, now()))
            self.management.event(db, 'local_administrator', 'campaign_registered', None, document)
        write_json(self.campaign_folder(identity)/'registration.json', document)
        return document

    def campaign_folder(self, identity):
        uuid.UUID(identity)
        return self.state/'campaigns'/identity

    def control(self, token, payload):
        self.management.admin(token)
        identity, command = payload['campaign'], payload['command']
        if command not in ('start', 'pause', 'resume', 'cancel', 'retry', 'aggregate'):
            raise ValueError('Invalid campaign control.')
        folder = self.campaign_folder(identity)
        with self.management.connection() as db:
            row = db.execute('SELECT * FROM campaigns WHERE id=?', (identity,)).fetchone()
            if not row:
                raise ValueError('Unknown campaign.')
            status = read_json((folder/'status.json')) if (folder/'status.json').exists() else {'state': row['status']}
            if status['state'] == 'completed':
                raise ValueError('Completed campaigns are immutable; register a new campaign.')
            if status['state']=='cancelled':
                raise ValueError('Cancelled campaigns cannot resume; register a new campaign.')
            if command=='resume' and status['state'] not in ('paused','running'):
                raise ValueError('Resume is for paused/running coordinators; use Start or Retry instead.')
            if command == 'retry' and status['state'] != 'failed':
                raise ValueError('Only failed campaigns can retry; existing successful steps are reused.')
            if command == 'start' and status['state'] not in ('created', 'waiting_for_terminal'):
                raise ValueError('Campaign already started; use resume or retry as appropriate.')
            if command in ('start', 'retry'):
                statuses = list(db.execute('SELECT joined FROM participation WHERE campaign=?', (identity,)))
                if not all(r['joined'] for r in statuses):
                    raise ValueError('All selected hospitals must opt in using Start local participation.')
            if command == 'aggregate':
                if status.get('phase') != 'aggregation_ready' or not status.get('round'):
                    raise ValueError('No validated round is awaiting aggregation approval.')
                rd=folder/f'round_{status["round"]:04d}'
                evidence=rd/'aggregation.json'
                if not evidence.exists(): raise ValueError('Aggregation evidence unavailable.')
                write_json(rd/'aggregation_approval.json',{'approved_utc':now(),'evidence_sha256':sha256(evidence),
                    'notice':'Execution approval only; documented acceptance decisions are unchanged.'})
            db.execute('UPDATE campaigns SET control=? WHERE id=?', ('run' if command in ('start','resume','retry','aggregate') else command, identity))
            if command=='start' and status['state']=='created':
                db.execute("UPDATE campaigns SET status='waiting_for_terminal' WHERE id=?",(identity,))
            if command=='cancel' and status['state'] in ('created','waiting_for_terminal'):
                write_json(folder/'status.json',{'state':'cancelled','phase':'cancelled_before_launch','updated_utc':now()})
            self.management.event(db, 'local_administrator', 'campaign_'+command, None, {'campaign': identity})
        return {'campaign': identity, 'requested': command,
            'launch_command': f'.\\.venv_runtime\\Scripts\\python.exe -u round_coordinator.py --campaign {identity}',
            'notice': 'For a new/retried process run this command in the visible VS Code terminal. No hidden training is launched. Pause/cancel take effect after the active step; retries reuse committed artifacts.'}

    def participate(self, token, payload):
        owner = self.owner(token)
        identity = payload['campaign']
        joined = payload.get('join') is True
        with self.management.connection() as db:
            row = db.execute('SELECT * FROM participation WHERE campaign=? AND hospital=?', (identity, owner['id'])).fetchone()
            if not row:
                raise PermissionError('Hospital is not in this campaign.')
            db.execute('UPDATE participation SET joined=?,updated=? WHERE campaign=? AND hospital=?',
                       (int(joined), now(), identity, owner['id']))
            self.management.event(db, owner['wallet'], 'participation_started' if joined else 'participation_stopped', owner['id'], {'campaign': identity})
        return {'campaign': identity, 'joined': joined,
                'notice': 'Stopping revokes participation at the next step/batch checkpoint. It does not erase submitted updates.'}

    def feedback(self, token, payload):
        self.management.admin(token)
        message = str(payload.get('message', '')).strip()
        if not 3 <= len(message) <= 1000:
            raise ValueError('Feedback must be 3ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ1000 characters and contain no patient information.')
        with self.management.connection() as db:
            if not db.execute('SELECT 1 FROM participation WHERE campaign=? AND hospital=?',
                              (payload['campaign'], payload['hospital'])).fetchone():
                raise ValueError('Hospital not enrolled in this campaign.')
            db.execute('INSERT INTO feedback(campaign,hospital,created,message) VALUES(?,?,?,?)',
                       (payload['campaign'], payload['hospital'], now(), message))
        return {'saved': True}

    def overview(self, token, admin=False):
        if admin:
            self.management.admin(token)
            owner = None
        else:
            owner = self.owner(token)
        with self.management.connection() as db:
            rows = list(db.execute('SELECT * FROM campaigns ORDER BY created DESC'))
            campaigns = []
            for row in rows:
                document = json.loads(row['document'])
                allowed = [p for p in document['participants'] if admin or p['id'] == owner['id']]
                if not allowed:
                    continue
                folder = self.campaign_folder(row['id'])
                status = read_json((folder/'status.json')) if (folder/'status.json').exists() else {'state': row['status']}
                rounds = []
                for path in sorted(folder.glob('round_*/public.json')):
                    value = read_json(path)
                    if not admin:
                        value['clients'] = [c for c in value.get('clients', []) if c['id'] == owner['id']]
                    rounds.append(value)
                item = {'registration': dict(document, participants=allowed), 'status': status,
                        'control': row['control'], 'rounds': rounds,
                        'participation': [dict(p) for p in db.execute('SELECT hospital,joined,updated FROM participation WHERE campaign=?', (row['id'],)) if admin or p['hospital'] == owner['id']],
                        'feedback': [dict(f) for f in db.execute('SELECT * FROM feedback WHERE campaign=? ORDER BY id', (row['id'],)) if admin or f['hospital'] == owner['id']]}
                if not admin:
                    # Coordinator errors/logs can contain another client's file paths.
                    item['status'] = {k:v for k,v in status.items() if k in ('state','round','phase','updated_utc','completed_round')}
                campaigns.append(item)
            clients = []
            for client in db.execute('SELECT * FROM portal_clients'):
                if not admin and client['hospital'] != owner['id']:
                    continue
                clients.append({'hospital': client['hospital'], 'delegate': client['delegate'],
                    'authorized_consent': bool(client['consent']), 'last_successful_sync':client['sync_utc'], 'data': json.loads(client['summary'] or 'null')})
                if not admin:
                    saved = read_json(Path(client['manifest'])) if client['manifest'] else None
                    root = self.folder(owner['id'])
                    clients[-1]['workspace_data_current'] = bool(saved) and all(
                        Path(path).is_relative_to(root) for path in saved['fingerprints'])
        result = {'campaigns': campaigns, 'clients': clients, 'approved_configurations': self.configurations(),
            'scope': 'Local client workers, no remote hospital or OS-level tenant isolation.',
            'comparison': 'FedAvg not run; no comparison data available.'}
        if not admin:
            result['data_folder'] = str(self.folder(owner['id']).resolve())
        return result

    def connectivity(self, token):
        self.management.admin(token)
        result = {}
        for name, factory in [('ipfs', lambda: LocalIPFS(progress_position=-1)), ('blockchain', Directory)]:
            try:
                factory(); result[name] = {'connected': True, 'checked_utc': now()}
            except Exception as exc:
                result[name] = {'connected': False, 'error': str(exc), 'checked_utc': now()}
        return result


    def export(self, token):
        self.management.admin(token)
        data = self.overview(token, admin=True)
        ids={item['registration']['id'] for item in data['campaigns']}
        with self.management.connection() as db:
            events=[]
            for row in db.execute('SELECT id,created,actor,action,hospital,detail FROM events ORDER BY id'):
                detail=json.loads(row['detail'])
                if detail.get('campaign') in ids or (row['action']=='campaign_registered' and detail.get('id') in ids):
                    events.append(dict(row))
        data['coordination_events']=events
        for item in data['campaigns']:
            attempts=[]
            for path in sorted((self.campaign_folder(item['registration']['id'])/'attempt_history').glob('*.json')):
                attempt=read_json(path)
                attempts.append({key:value for key,value in attempt.items() if key in ('state','phase','round','updated_utc','completed_round')})
            item['prior_execution_attempts']=attempts
        data['exported_utc'] = now()
        data['export_note'] = 'Coordination metadata and approved evaluation only; no raw images, patient manifests or key files.'
        return data

    def local_log(self, token, campaign, number):
        owner = self.owner(token, require_approved=False)
        folder = self.campaign_folder(campaign)
        with self.management.connection() as db:
            enrolled=db.execute('SELECT 1 FROM participation WHERE campaign=? AND hospital=?',(campaign,owner['id'])).fetchone()
        if not enrolled: raise PermissionError('Hospital not in this campaign.')
        registration = read_json((folder/'registration.json'))
        index = next((i for i,p in enumerate(registration['participants']) if p['id'] == owner['id']), None)
        if index is None:
            raise PermissionError('Hospital not in this campaign.')
        if number not in range(1, registration['rounds']+1):
            raise ValueError('Invalid round.')
        private = folder/f'round_{number:04d}'/'private.json'
        if not private.exists():
            return {'log':'No local attempt recorded.'}
        job = json.loads(private.read_text())['jobs'].get(str(index))
        if not job:
            return {'log':'No local attempt recorded.'}
        local = Path(job['folder']).resolve()
        allowed = (self.state/'agents'/owner['id']).resolve()
        if not local.is_relative_to(allowed):
            raise PermissionError('Local artifact path outside owner scope.')
        log = local/'training.log'
        text=''
        if log.exists():
            with log.open('rb') as stream:
                stream.seek(max(0,log.stat().st_size-16000)); text=stream.read().decode('utf-8',errors='replace')
        return {'log':text,'progress':json.loads((local/'progress.json').read_text()) if (local/'progress.json').exists() else None,
                'error':json.loads((local/'error.json').read_text()) if (local/'error.json').exists() else None}

    def model(self, token, campaign, version):
        try:
            self.management.admin(token)
        except PermissionError:
            owner=self.owner(token)
            registered=json.loads((self.campaign_folder(campaign)/'registration.json').read_text())
            if owner['id'] not in [p['id'] for p in registered['participants']]:
                raise PermissionError('This hospital is not enrolled in the selected campaign.')
        folder=self.campaign_folder(campaign)
        if version=='best':
            version=read_json((folder/'execution'/'selection.json'))['best_round']
        version=int(version)
        registered=read_json((folder/'registration.json'))
        if version not in range(1,registered['rounds']+1):
            raise ValueError('Unknown campaign global version.')
        reference=read_json((folder/f'round_{version:04d}'/'global.json'))
        checkpoint=folder/'execution'/f'global_round_{version:04d}.pt'
        if sha256(checkpoint)!=reference['sha256']:
            raise ValueError('Campaign model hash mismatch.')
        return checkpoint,reference,version
