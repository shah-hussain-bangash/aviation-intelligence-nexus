from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from infra.recovery import database_facts
from infra.schema_preflight import inspect_snapshot
from services.api.main import create_app, initialize
from services.api.auth import AuthStore
from services.api.account_security import account_sessions
from services.api.security_audit import AUDIT_TABLE_SQL, AUDIT_TRIGGER_SQL, AuditContractError, require_audit_contract


class AuditContractTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(); self.path = Path(self.folder.name) / 'synthetic.sqlite3'
        initialize(self.path); self.auth = AuthStore(self.path); self.password = 'synthetic-contract-password-123'
        self.auth.create_user('synthetic-admin', self.password, 'admin')

    def tearDown(self):
        self.folder.cleanup()

    def execute(self, sql):
        with closing(sqlite3.connect(self.path)) as db, db:db.execute(sql)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return '\n'.join(db.iterdump())

    def test_valid_contract_is_read_only_and_tolerates_migration_whitespace(self):
        self.execute('DROP TABLE security_audit')
        self.execute(AUDIT_TABLE_SQL.replace('    ', '\t'))
        for sql in AUDIT_TRIGGER_SQL.values():self.execute(sql.replace(' BEFORE ', '\nBEFORE\n'))
        before = self.dump(); statements = []
        with closing(sqlite3.connect(self.path)) as db:
            db.set_trace_callback(statements.append); require_audit_contract(db)
            self.assertFalse(db.in_transaction)
        self.assertTrue(all(s.startswith(('SELECT', 'PRAGMA')) for s in statements), statements)
        self.assertEqual(before, self.dump())
        initialize(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0], 8)

    def test_missing_dummy_and_additional_audit_triggers_are_rejected(self):
        variants = [None,
            'CREATE TRIGGER security_audit_no_update BEFORE UPDATE ON security_audit BEGIN SELECT 1; END',
            'CREATE TRIGGER unexpected_audit_trigger AFTER INSERT ON security_audit BEGIN SELECT 1; END']
        for replacement in variants:
            with self.subTest(replacement=replacement):
                self.execute('DROP TRIGGER security_audit_no_update')
                if replacement:self.execute(replacement)
                with closing(sqlite3.connect(self.path)) as db:
                    with self.assertRaisesRegex(AuditContractError, '^audit_schema_contract_invalid$'):require_audit_contract(db)
                if replacement:self.execute('DROP TRIGGER ' + ('unexpected_audit_trigger' if 'unexpected' in replacement else 'security_audit_no_update'))
                self.execute(AUDIT_TRIGGER_SQL['security_audit_no_update'])

    def test_changed_table_definition_is_rejected_even_with_expected_columns_and_triggers(self):
        self.execute('DROP TABLE security_audit')
        self.execute(AUDIT_TABLE_SQL.replace('event_id TEXT NOT NULL UNIQUE', 'event_id TEXT NOT NULL'))
        for sql in AUDIT_TRIGGER_SQL.values():self.execute(sql)
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaises(AuditContractError):require_audit_contract(db)

    def test_disabled_connection_safeguards_are_rejected_without_repair(self):
        for setting in ('checks', 'writable_schema', 'triggers'):
            with self.subTest(setting=setting), closing(sqlite3.connect(self.path)) as db:
                if setting == 'checks':db.execute('PRAGMA ignore_check_constraints=ON')
                elif setting == 'writable_schema':db.execute('PRAGMA writable_schema=ON')
                else:db.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_TRIGGER, False)
                with self.assertRaisesRegex(AuditContractError, 'audit_connection_safeguards_disabled'):require_audit_contract(db)
                if setting == 'checks':self.assertEqual(db.execute('PRAGMA ignore_check_constraints').fetchone()[0], 1)
                elif setting == 'writable_schema':self.assertEqual(db.execute('PRAGMA writable_schema').fetchone()[0], 1)
                else:self.assertFalse(db.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_TRIGGER))

    def test_every_covered_identity_mutation_rolls_back_with_missing_guard(self):
        self.auth.create_user('synthetic-viewer', self.password, 'viewer')
        first = self.auth.login('synthetic-admin', self.password); other = self.auth.login('synthetic-admin', self.password)
        self.execute('DROP TRIGGER security_audit_no_update'); before = self.dump()
        actions = [lambda:self.auth.login('synthetic-admin', self.password),
                   lambda:self.auth.login('unknown-fixture', 'bad-password'),
                   lambda:self.auth.logout(first), lambda:self.auth.create_user('new-fixture', self.password, 'viewer'),
                   lambda:self.auth.set_access('synthetic-viewer', role='researcher'),
                   lambda:account_sessions(self.path, first, revoke_others=True)]
        for action in actions:
            with self.assertRaises(AuditContractError):action()
            self.assertEqual(before, self.dump())
        self.assertIsNotNone(self.auth.session(first)); self.assertIsNotNone(self.auth.session(other))

    def test_startup_refuses_missing_guard_before_journal_changes_or_worker_hooks(self):
        self.execute('DROP TRIGGER security_audit_no_delete')
        with closing(sqlite3.connect(self.path)) as db:db.execute('PRAGMA journal_mode=DELETE')
        before = self.path.read_bytes()
        with patch('agents.store.AgentStore.recover') as recover, patch('agents.jobs.JobWorker.start') as worker, patch('services.api.monitoring.Monitor.start') as monitor:
            with self.assertRaises(AuditContractError):
                with TestClient(create_app(self.path)):self.fail('must not start')
            recover.assert_not_called(); worker.assert_not_called(); monitor.assert_not_called()
        self.assertEqual(before, self.path.read_bytes())

    def test_runtime_missing_guard_changes_health_and_refuses_login_logout_and_audit_read(self):
        with TestClient(create_app(self.path)) as client:
            response = client.post('/api/v1/auth/login', json={'username':'synthetic-admin','password':self.password}, headers={'Origin':'http://127.0.0.1:8080'})
            self.assertEqual(response.status_code, 200)
            self.execute('DROP TRIGGER security_audit_no_update')
            self.assertEqual(client.get('/health/live').status_code, 200)
            self.assertEqual(client.get('/health/ready').status_code, 503)
            self.assertEqual(client.get('/api/v1/status').status_code, 503)
            self.assertEqual(client.get('/api/v1/research/security-audit').status_code, 503)
            with patch('rag.ollama.models', return_value=[]):
                self.assertFalse(client.get('/api/v1/research/platform-status').json()['database_ready'])
            headers = {'Origin':'http://127.0.0.1:8080','X-CSRF-Token':response.json()['csrf_token']}
            self.assertEqual(client.post('/api/v1/auth/logout', json={}, headers=headers).status_code, 503)
            self.assertTrue(client.get('/api/v1/auth/session').json()['authenticated'])
            failed = client.post('/api/v1/auth/login', json={'username':'synthetic-admin','password':self.password}, headers=headers)
            self.assertEqual(failed.status_code, 503); self.assertNotIn(self.password, failed.text)
            # Manual repair of an intentionally broken synthetic fixture only.
            self.execute(AUDIT_TRIGGER_SQL['security_audit_no_update'])
            self.assertEqual(client.get('/health/ready').status_code, 200)

    def test_backup_and_offline_inspection_reject_missing_guard_without_repair(self):
        self.execute('DROP TRIGGER security_audit_no_update')
        # Standalone offline fixture, without live WAL sidecars.
        with closing(sqlite3.connect(self.path)) as db:db.execute('PRAGMA journal_mode=DELETE')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'audit schema'):database_facts(self.path)
        report = inspect_snapshot(self.path, offline_snapshot=True)
        self.assertFalse(report['local_schema_checks_passed']); self.assertEqual(report['errors'], ['audit_schema_contract_invalid'])
        self.assertEqual(before, self.path.read_bytes()); self.assertFalse(report['production_ready'])
