"""Local organization onboarding, wallet sessions and future-run enrollment."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid

from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from architecture_io import write_json
from blockchain.hospital_directory import Directory

ROOT = Path(__file__).resolve().parent
STATE = ROOT/'local_operations'

# Immutable hash namespace used by existing on-chain hospital commitments.
# This is a protocol compatibility value, not the current display name.
ORGANIZATION_COMMITMENT_DOMAIN = 'PneumoLedger organization:'


def now():
    return datetime.now(timezone.utc).isoformat()


def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Management:
    def __init__(self, state=STATE):
        self.state = Path(state)
        self.state.mkdir(exist_ok=True)
        self.keyfile = self.state/'admin.key'
        if not self.keyfile.exists():
            with self.keyfile.open('x', encoding='utf-8') as stream:
                stream.write(secrets.token_urlsafe(48))
        self.db = self.state/'organizations.sqlite3'
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS hospitals (
                    id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    wallet TEXT UNIQUE NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL,
                    updated TEXT NOT NULL, heartbeat TEXT, readiness TEXT, receipt TEXT);
                CREATE TABLE IF NOT EXISTS challenges (
                    wallet TEXT PRIMARY KEY, message TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, wallet TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL,
                    actor TEXT NOT NULL, action TEXT NOT NULL, hospital TEXT, detail TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rosters (
                    id TEXT PRIMARY KEY, created TEXT NOT NULL, content TEXT NOT NULL);
            ''')

    def connection(self):
        db = sqlite3.connect(self.db, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def admin(self, token):
        expected = self.keyfile.read_text(encoding='utf-8').strip()
        if not token or not hmac.compare_digest(token, expected):
            raise PermissionError('Administrator token required.')

    @staticmethod
    def event(db, actor, action, hospital, detail):
        db.execute('INSERT INTO events(created,actor,action,hospital,detail) VALUES(?,?,?,?,?)',
                   (now(), actor, action, hospital, json.dumps(detail)))

    def challenge(self, wallet):
        wallet = Web3.to_checksum_address(wallet)
        nonce = secrets.token_urlsafe(32)
        message = ('Fed-Ledger local hospital portal\nOrigin: http://127.0.0.1:8765\n'
                   f'Wallet: {wallet}\nPurpose: hospital portal login only\n'
                   f'Nonce: {nonce}\nIssued: {now()}\nExpires in 5 minutes. No transaction authorized.')
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO challenges VALUES(?,?,?)', (wallet, message, time.time()+300))
        return {'message': message, 'expires_in_seconds': 300}

    def login(self, wallet, signature):
        wallet = Web3.to_checksum_address(wallet)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM challenges WHERE wallet=?', (wallet,)).fetchone()
            if row is None or row['expires'] < time.time():
                raise PermissionError('Challenge missing or expired; request a fresh challenge.')
            recovered = Account.recover_message(encode_defunct(text=row['message']), signature=signature)
            if recovered != wallet:
                raise PermissionError('Signature does not match wallet.')
            token = secrets.token_urlsafe(48)
            db.execute('DELETE FROM challenges WHERE wallet=?', (wallet,))
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashed(token), wallet, time.time()+8*3600))
            self.event(db, wallet, 'wallet_login', None, {})
        return {'token': token, 'wallet': wallet, 'expires_in_seconds': 8*3600}

    def wallet(self, token):
        with self.connection() as db:
            row = db.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>?', (hashed(token), time.time())).fetchone()
        if row is None:
            raise PermissionError('Wallet session missing or expired.')
        return row['wallet']

    def logout(self, token):
        with self.connection() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (hashed(token),))
        return {'signed_out': True}

    def register(self, token, payload):
        wallet = self.wallet(token)
        code = str(payload.get('code', '')).strip().upper()
        name = str(payload.get('name', '')).strip()
        if re.fullmatch(r'CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9]', code):
            raise ValueError('Choose a hospital code that is not a reserved Windows folder name.')
        if not re.fullmatch(r'[A-Z0-9_-]{3,32}', code) or not 3 <= len(name) <= 120:
            raise ValueError('Organization code: 3–32 letters/digits/_/-. Name: 3–120 characters.')
        identity = str(uuid.uuid4())
        with self.connection() as db:
            try:
                db.execute('INSERT INTO hospitals(id,code,name,wallet,status,created,updated) VALUES(?,?,?,?,?,?,?)',
                           (identity, code, name, wallet, 'pending', now(), now()))
            except sqlite3.IntegrityError:
                raise ValueError('Organization code or wallet already registered.') from None
            self.event(db, wallet, 'application_submitted', identity, {'code': code})
        return {'id': identity, 'status': 'pending'}

    def transition(self, token, payload):
        self.admin(token)
        identity, action = payload.get('id'), payload.get('action')
        reason = str(payload.get('reason', '')).strip()
        if action not in ('approve', 'reject', 'suspend'):
            raise ValueError('Provide approve, reject or suspend.')
        if len(reason) > 500:
            raise ValueError('Optional review reason must be at most 500 characters.')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM hospitals WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise ValueError('Hospital not found.')
            permitted = {'approve': ('pending', 'suspended'), 'reject': ('pending',), 'suspend': ('approved',)}
            if row['status'] not in permitted[action]:
                raise ValueError('Invalid status transition.')
            receipt = None
            target = {'approve': 'approved', 'reject': 'rejected', 'suspend': 'suspended'}[action]
            if action != 'reject':
                directory = Directory()
                commitment = '0x'+hashed(ORGANIZATION_COMMITMENT_DOMAIN+row['id'])
                receipt = directory.set(row['wallet'], commitment, action == 'approve')
            # Chain commitment is applied before local state; reconciliation checks expose divergence.
            db.execute('UPDATE hospitals SET status=?,updated=?,receipt=? WHERE id=?',
                       (target, now(), json.dumps(receipt), identity))
            self.event(db, 'local_administrator', action, identity, {'reason': reason, 'receipt': receipt})
        return {'id': identity, 'status': target, 'receipt': receipt}

    def heartbeat(self, token, payload):
        wallet = self.wallet(token)
        samples = payload.get('sample_count')
        if isinstance(samples, bool) or not isinstance(samples, int) or not 1 <= samples <= 10000000:
            raise ValueError('Positive integer sample_count required; do not send image data.')
        readiness = {key: payload.get(key) is True for key in
                     ('patient_split_checked', 'labels_checked', 'local_data_only', 'client_ready')}
        readiness['sample_count'] = samples
        with self.connection() as db:
            row = db.execute('SELECT * FROM hospitals WHERE wallet=?', (wallet,)).fetchone()
            if row is None or row['status'] != 'approved':
                raise PermissionError('Only an approved hospital can report readiness.')
            directory = Directory()
            member = directory.membership(wallet)
            if not member['authorized']:
                raise PermissionError('Hospital wallet is not authorized in the live directory.')
            db.execute('UPDATE hospitals SET heartbeat=?,readiness=?,updated=? WHERE wallet=?',
                       (now(), json.dumps(readiness), now(), wallet))
        return {'received_utc': now(), 'readiness_is': 'self-reported, not independently verified'}

    def roster(self, token, payload):
        self.admin(token)
        ids = payload.get('hospital_ids', [])
        if not isinstance(ids, list) or len(ids) != 3 or len(set(ids)) != 3:
            raise ValueError('Current peer protocol requires exactly three distinct approved hospitals.')
        directory = Directory()
        with self.connection() as db:
            hospitals = []
            for identity in ids:
                row = db.execute('SELECT * FROM hospitals WHERE id=?', (identity,)).fetchone()
                if row is None or row['status'] != 'approved':
                    raise ValueError('All selected hospitals must be approved.')
                readiness = json.loads(row['readiness'] or '{}')
                fresh = row['heartbeat'] and (datetime.now(timezone.utc)-datetime.fromisoformat(row['heartbeat'])).total_seconds() <= 120
                if not fresh or not all(readiness.get(key) is True for key in
                        ('patient_split_checked', 'labels_checked', 'local_data_only', 'client_ready')):
                    raise ValueError('Fresh heartbeat (within 120s) and all readiness declarations required.')
                if not directory.membership(row['wallet'])['authorized']:
                    raise ValueError('Selected wallet is not authorized on-chain.')
                hospitals.append({key: row[key] for key in ('id', 'code', 'wallet')})
            roster_id = str(uuid.uuid4())
            policy = json.loads((ROOT/'architecture_protocol.json').read_text())
            document = {'id': roster_id, 'created_utc': now(), 'hospitals': hospitals,
                'policy_sha256': hashlib.sha256((ROOT/'architecture_protocol.json').read_bytes()).hexdigest(),
                'policy': policy, 'state': 'eligible_local_three_hospital_enrollment_snapshot',
                'notice': 'No historical membership changed. Use --roster-file for a separately authorized future local run; saving this snapshot launches no jobs.'}
            db.execute('INSERT INTO rosters VALUES(?,?,?)', (roster_id, now(), json.dumps(document)))
            self.event(db, 'local_administrator', 'future_roster_created', None, {'roster_id': roster_id})
        write_json(self.state/'rosters'/(roster_id+'.json'), document)
        return document

    def list(self, token=None):
        with self.connection() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM hospitals ORDER BY created')]
            events = [dict(row) for row in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]
            rosters = [json.loads(row['content']) for row in db.execute('SELECT content FROM rosters ORDER BY created DESC')]
        for row in rows:
            row['readiness'] = json.loads(row['readiness'] or '{}')
            row['receipt'] = json.loads(row['receipt'] or 'null')
            row['online'] = bool(row['heartbeat'] and
                (datetime.now(timezone.utc)-datetime.fromisoformat(row['heartbeat'])).total_seconds() <= 120)
        if token:
            self.admin(token)
            try:
                directory = Directory()
                directory_status = {'connected': True, 'contract': directory.contract.address, 'chain_id': directory.client.eth.chain_id}
                for row in rows:
                    member = directory.membership(row['wallet'])
                    row['directory_membership'] = member
                    row['reconciliation_ok'] = (member['authorized'] == (row['status'] == 'approved') and
                        (member['organization_hash'] == '0x'+hashed(ORGANIZATION_COMMITMENT_DOMAIN+row['id'])
                         if row['status'] in ('approved', 'suspended') else True))
            except Exception as exc:
                directory_status = {'connected': False, 'error': str(exc)}
            return {'hospitals': rows, 'events': events, 'rosters': rosters, 'directory': directory_status}
        # Public local view excludes application organization names, wallet addresses and reasons.
        return {'hospitals': [{key: row[key] for key in ('id', 'code', 'status', 'online')} for row in rows]}

    def me(self, token):
        wallet = self.wallet(token)
        with self.connection() as db:
            row = db.execute('SELECT * FROM hospitals WHERE wallet=?', (wallet,)).fetchone()
        with self.connection() as db:
            events = [dict(event) for event in db.execute(
                "SELECT created,action,detail FROM events WHERE hospital=? AND action IN ('approve','reject','suspend') ORDER BY id DESC LIMIT 20",
                (row['id'],))] if row else []
        return {'wallet': wallet, 'application': dict(row) if row else None, 'review_feedback': events}


def load_roster(path):
    """Resolve approved local wallets for a future, separately authorized run."""
    from eth_account import Account
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    management = Management()
    with management.connection() as db:
        stored = db.execute('SELECT content FROM rosters WHERE id=?', (data['id'],)).fetchone()
        if stored is None or json.loads(stored['content']) != data:
            raise ValueError('Roster snapshot differs from the saved administrator-approved document.')
        if data['policy_sha256'] != hashlib.sha256((ROOT/'architecture_protocol.json').read_bytes()).hexdigest():
            raise ValueError('Registered policy changed since enrollment.')
        directory = Directory()
        wallets, signers = [], {}
        for item in data['hospitals']:
            row = db.execute('SELECT * FROM hospitals WHERE id=?', (item['id'],)).fetchone()
            if row is None or row['status'] != 'approved' or row['wallet'] != item['wallet']:
                raise ValueError('Hospital no longer approved or wallet changed.')
            if not row['heartbeat'] or (datetime.now(timezone.utc)-datetime.fromisoformat(row['heartbeat'])).total_seconds() > 120:
                raise ValueError('Hospital heartbeat is stale; refresh it before launch.')
            member = directory.membership(row['wallet'])
            if not member['authorized'] or member['organization_hash'] != '0x'+hashed(ORGANIZATION_COMMITMENT_DOMAIN+row['id']):
                raise ValueError('Hospital authorization does not match this organization on chain.')
            readiness = json.loads(row['readiness'] or '{}')
            if not all(readiness.get(key) is True for key in ('patient_split_checked', 'labels_checked', 'local_data_only', 'client_ready')):
                raise ValueError('Client readiness declarations are incomplete.')
            keyfile = management.state/'clients'/row['code']/'wallet.key'
            if not keyfile.is_file():
                raise ValueError('Local simulation requires a local hospital_client wallet; external wallet execution is not implemented.')
            signer = Account.from_key(keyfile.read_text(encoding='utf-8').strip())
            if signer.address != row['wallet']:
                raise ValueError('Local client key differs from approved wallet.')
            wallets.append(row['wallet']); signers[row['wallet']] = signer
    if len(wallets) != 3 or len(set(wallets)) != 3:
        raise ValueError('Current protocol requires three distinct clients.')
    return data, wallets, signers
