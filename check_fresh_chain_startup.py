"""Isolated startup/migration checks: no live RPC, deployments, services or training."""
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from architecture_io import write_json
from hospital_management import Management
from portal_workflow import Workflow
import start_local_system as startup

ROOT = Path(__file__).resolve().parent
ORIGINAL_MATCHING = startup.matching_contracts
NAMES = ('protocol', 'directory', 'client')


class StartupChecks(unittest.TestCase):
    def setUp(self):
        self.root = ROOT/'local_operations'/'startup_check_fixtures'/uuid.uuid4().hex
        self.root.mkdir(parents=True)
        (self.root/'blockchain').mkdir()
        self.management = Management(self.root/'local_operations')
        self.runtime = {'listening': False, 'instance': 'fixture-new', 'locked': False}
        self.deployments = {name: 0 for name in NAMES}
        self.starts = []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(startup, 'ROOT', self.root))
        self.stack.enter_context(patch.object(startup, 'record', lambda message: None))
        self.stack.enter_context(patch.object(startup, 'listening', lambda port: self.runtime['listening']))
        self.stack.enter_context(patch.object(startup, 'connect', lambda: object()))
        self.stack.enter_context(patch.object(startup, 'instance_id', lambda client: self.runtime['instance']))
        self.stack.enter_context(patch.object(startup, 'start', self.start))
        self.stack.enter_context(patch.object(startup, 'training_guard', self.guard))
        self.stack.enter_context(patch.object(startup, 'matching_contracts', self.matching))
        for name in NAMES:
            self.stack.enter_context(patch.object(startup, 'deploy_'+name, lambda name=name: self.deploy(name)))
        for name in NAMES:
            write_json(self.pointer(name), {'instance_id': 'fixture-old', 'address': name+'-old'})

    def pointer(self, name):
        return self.root/'blockchain'/('deployment.'+name+'.local.json')

    def start(self, name):
        self.assertEqual(name, 'hardhat')
        self.starts.append(name)
        self.runtime['listening'] = True

    @contextmanager
    def guard(self):
        if self.runtime['locked']:
            raise RuntimeError('Another training or migration holds the lock')
        yield

    def deploy(self, name):
        path = self.pointer(name)
        if path.exists():
            self.assertEqual(json.loads(path.read_text())['instance_id'], self.runtime['instance'])
            return
        self.deployments[name] += 1
        write_json(path, {'instance_id': self.runtime['instance'], 'address': name+'-new'})

    def matching(self):
        for name in NAMES:
            if not self.pointer(name).exists() or json.loads(self.pointer(name).read_text())['instance_id'] != self.runtime['instance']:
                raise RuntimeError('Contract unavailable on this instance')
        return SimpleNamespace(instance=self.runtime['instance'], contract=SimpleNamespace(address='protocol-new'))

    def campaign(self, state, rounds=1, history=None):
        Workflow(self.management)
        identity = str(uuid.uuid4())
        folder = self.management.state/'campaigns'/identity
        document = {'rounds': rounds}
        with self.management.connection() as db:
            db.execute('INSERT INTO campaigns VALUES(?,?,?,?,?)', (identity, 'fixture', json.dumps(document), 'waiting_for_terminal', 'run'))
        status = {'state': state, 'completed_round': rounds if state == 'completed' else 0,
                  'error': 'fixture failure' if state == 'failed' else None}
        write_json(folder/'status.json', status)
        write_json(folder/'registration.json', document)
        if history is not None:
            write_json(folder/'execution/history.json', history)
        return identity, folder

    def journal(self):
        return json.loads((self.management.state/'chain_migration_current.json').read_text())

    def test_empty_install_initializes_tables_and_archives(self):
        chain = startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(chain.instance, 'fixture-new')
        self.assertEqual(self.deployments, dict.fromkeys(NAMES, 1))
        self.assertEqual(self.journal()['state'], 'complete')
        with self.management.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM portal_clients').fetchone()[0], 0)
        self.assertTrue((Path(self.journal()['archive'])/'organizations.sqlite3').exists())

    def test_matching_chain_is_reused_even_with_fresh_flag(self):
        for name in NAMES:
            write_json(self.pointer(name), {'instance_id': 'fixture-new'})
        self.runtime['listening'] = True
        startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(sum(self.deployments.values()), 0)
        self.assertEqual(self.starts, [])
        self.assertFalse((self.management.state/'chain_archives').exists())

    def test_missing_chain_requires_explicit_flag(self):
        with self.assertRaisesRegex(RuntimeError, '--fresh-chain'):
            startup.ensure_chain(self.management)
        self.assertEqual(self.starts, [])

    def test_foreign_rpc_cannot_be_overridden_by_fresh_flag(self):
        self.runtime['listening'] = True
        before = self.pointer('protocol').read_bytes()
        with patch.object(startup, 'connect', side_effect=RuntimeError('Wrong RPC service')):
            with self.assertRaisesRegex(RuntimeError, 'Wrong RPC'):
                startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(self.pointer('protocol').read_bytes(), before)
        self.assertFalse((self.management.state/'chain_archives').exists())

    def test_active_campaign_blocks_replacement(self):
        self.campaign('running')
        with self.assertRaisesRegex(RuntimeError, 'Unfinished campaign'):
            startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(self.starts, [])

    def test_training_lock_blocks_replacement(self):
        self.runtime['locked'] = True
        with self.assertRaisesRegex(RuntimeError, 'lock'):
            startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(self.starts, [])

    def test_competing_startup_completed_before_lock_is_reused(self):
        @contextmanager
        def completed_elsewhere():
            self.runtime['listening'] = True
            for name in NAMES:
                write_json(self.pointer(name), {'instance_id': 'fixture-new'})
            yield
        with patch.object(startup, 'training_guard', completed_elsewhere):
            startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(self.starts, [])
        self.assertEqual(sum(self.deployments.values()), 0)
        self.assertFalse((self.management.state/'chain_archives').exists())

    def test_failed_campaign_is_archived_without_erasing_failure(self):
        identity, folder = self.campaign('failed')
        original = (folder/'status.json').read_bytes()
        startup.ensure_chain(self.management, fresh=True)
        self.assertEqual((Path(self.journal()['archive'])/'campaigns'/identity/'status.json').read_bytes(), original)
        self.assertEqual((folder/'status.json').read_bytes(), original)
        with self.management.connection() as db:
            self.assertEqual(db.execute('SELECT status FROM campaigns WHERE id=?', (identity,)).fetchone()[0], 'failed')

    def test_completed_evidence_requires_all_distinct_rounds(self):
        self.campaign('completed', rounds=2, history=[{'round': 1}, {'round': 1}])
        with self.assertRaisesRegex(RuntimeError, 'evidence incomplete'):
            startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(self.starts, [])

    def test_valid_completed_and_cancelled_history_is_preserved(self):
        self.campaign('completed', history=[{'round': 1}])
        self.campaign('cancelled')
        startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(len(self.journal()['historical_campaigns']), 2)

    def fail_directory_once(self):
        def failure():
            raise RuntimeError('fixture deployment interrupted')
        with patch.object(startup, 'deploy_directory', failure):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                startup.ensure_chain(self.management, fresh=True)

    def test_partial_deployment_resumes_without_redeploying_protocol(self):
        self.fail_directory_once()
        archive = self.journal()['archive']
        self.assertEqual(self.journal()['state'], 'in_progress')
        startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(self.journal()['archive'], archive)
        self.assertEqual(self.deployments, dict.fromkeys(NAMES, 1))

    def test_resume_refuses_changed_backup(self):
        self.fail_directory_once()
        (Path(self.journal()['archive'])/self.pointer('protocol').name).write_text('changed fixture')
        with self.assertRaisesRegex(RuntimeError, 'backup changed'):
            startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(self.deployments['directory'], 0)

    def test_reset_clears_permissions_but_preserves_data_and_keys(self):
        Workflow(self.management)
        identity = str(uuid.uuid4())
        marker = self.management.state/'hospital_data'/'FIXTURE'/'original.dat'
        marker.parent.mkdir(parents=True)
        marker.write_bytes(b'original fixture bytes')
        key = self.management.state/'agents'/identity/'client.key'
        key.parent.mkdir(parents=True)
        key.write_text('fixture only, not a usable private key')
        with self.management.connection() as db:
            db.execute('INSERT INTO hospitals(id,code,name,wallet,status,created,updated,receipt,heartbeat,readiness) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (identity, 'FIXTURE', 'Fixture hospital', 'fixture-wallet', 'approved', 'old', 'old', '{}', 'old', '{}'))
            db.execute('INSERT INTO portal_clients(hospital,manifest,summary,consent,receipt,message,expires) VALUES(?,?,?,?,?,?,?)',
                       (identity, 'preserved-manifest', '{}', 'old-consent', '{}', 'old-message', 300))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', ('fixture-token-hash', 'fixture-wallet', 9999999999))
        startup.ensure_chain(self.management, fresh=True)
        with self.management.connection() as db:
            h = db.execute('SELECT * FROM hospitals').fetchone()
            c = db.execute('SELECT * FROM portal_clients').fetchone()
            self.assertEqual(h['status'], 'pending')
            self.assertIsNone(h['receipt'])
            self.assertIsNone(c['consent'])
            self.assertEqual(c['manifest'], 'preserved-manifest')
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)
        self.assertEqual(marker.read_bytes(), b'original fixture bytes')
        self.assertEqual(key.read_text(), 'fixture only, not a usable private key')

    def test_enrollment_transaction_failure_recovers(self):
        Workflow(self.management)
        with patch.object(Management, 'event', side_effect=RuntimeError('fixture database interruption')):
            with self.assertRaisesRegex(RuntimeError, 'database interruption'):
                startup.ensure_chain(self.management, fresh=True)
        startup.ensure_chain(self.management, fresh=True)
        self.assertEqual(self.journal()['state'], 'complete')
        self.assertEqual(self.deployments, dict.fromkeys(NAMES, 1))

    def test_all_contracts_and_directory_dependency_are_checked(self):
        chain = SimpleNamespace(instance='fixture', contract=SimpleNamespace(address='protocol'))
        directory = SimpleNamespace(instance='fixture', contract=SimpleNamespace(address='correct-directory'))
        delegate = SimpleNamespace(instance='fixture', contract=SimpleNamespace(functions=SimpleNamespace(
            directory=lambda: SimpleNamespace(call=lambda: 'wrong-directory'))))
        with patch.object(startup, 'ProtocolChain', return_value=chain), patch.object(startup, 'Directory', return_value=directory), patch.object(startup, 'ClientAuthorization', return_value=delegate):
            with self.assertRaisesRegex(RuntimeError, 'different hospital directory'):
                ORIGINAL_MATCHING()


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StartupChecks))
    write_json(ROOT/'multiseed_outputs/fresh_chain_startup_checks.json', {
        'tests_run': result.testsRun, 'passed': result.testsRun-len(result.failures)-len(result.errors),
        'failures': [trace for _, trace in result.failures], 'errors': [trace for _, trace in result.errors],
        'live_chain_modified': False, 'scope': 'isolated mocked RPC/services; fixtures retained under local_operations/startup_check_fixtures'})
    raise SystemExit(0 if result.wasSuccessful() else 1)
