from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from services.api.main import create_app, initialize
from services.api.migrations import MigrationHistoryError, history_version, require_current


class StartupMigrationTests(unittest.TestCase):
    def execute(self, path, sql):
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(sql)

    def dump(self, path):
        with closing(sqlite3.connect(path)) as db:
            return '\n'.join(db.iterdump())

    def test_fresh_initialization_and_concurrent_restarts_preserve_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.sqlite3'; initialize(path)
            self.execute(path, "INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES ('synthetic','1','2025-01-01','XX','AAA','BBB')")
            before = self.dump(path)
            with ThreadPoolExecutor(max_workers=4) as workers:
                list(workers.map(lambda _: initialize(path), range(8)))
            self.assertEqual(before, self.dump(path))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(history_version(db, 8), 8)

    def test_gapped_and_newer_histories_stop_before_journal_or_migration_writes(self):
        for sql, code in [
            ('DELETE FROM schema_migrations WHERE version=4', 'migration_history_gap'),
            ('INSERT INTO schema_migrations(version) VALUES (9)', 'migration_history_newer_than_service')]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'synthetic.sqlite3'; initialize(path); self.execute(path, sql)
                with closing(sqlite3.connect(path)) as db:
                    db.execute('PRAGMA journal_mode=DELETE')
                before = path.read_bytes(); statements = []
                db = sqlite3.connect(path); db.set_trace_callback(statements.append)
                with patch('services.api.main.connect', return_value=db):
                    with self.assertRaisesRegex(MigrationHistoryError, '^' + code + '$'):
                        initialize(path)
                self.assertEqual(before, path.read_bytes())
                self.assertFalse(any(s.startswith(('BEGIN', 'CREATE', 'INSERT', 'ALTER', 'PRAGMA journal_mode')) for s in statements), statements)

    def test_missing_empty_invalid_and_view_histories_cannot_adopt_existing_state(self):
        setups = [
            ['CREATE TABLE private_state(value TEXT)'],
            ['CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT)', 'CREATE TABLE private_state(value TEXT)'],
            ['CREATE VIEW schema_migrations AS SELECT 7 AS version'],
            ['CREATE TABLE schema_migrations(version TEXT PRIMARY KEY,applied_at TEXT)', "INSERT INTO schema_migrations VALUES ('PRIVATE-VERSION',NULL)"],
            ['CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT)', 'INSERT INTO schema_migrations VALUES (0,NULL)']]
        for setup in setups:
            with self.subTest(setup=setup[0]), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'synthetic.sqlite3'
                for sql in setup:
                    self.execute(path, sql)
                before = self.dump(path)
                with self.assertRaises(MigrationHistoryError) as error:
                    initialize(path)
                self.assertNotIn('PRIVATE', str(error.exception)); self.assertNotIn(folder, str(error.exception))
                self.assertEqual(before, self.dump(path))

    def test_history_is_rechecked_under_lock_before_migration_ddl(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.sqlite3'; initialize(path)
            statements = []; db = sqlite3.connect(path); db.set_trace_callback(statements.append)
            real = history_version; calls = []
            def changed(connection, expected, **kwargs):
                calls.append(len(calls))
                if len(calls) == 2:
                    raise MigrationHistoryError('migration_history_gap')
                return real(connection, expected, **kwargs)
            with patch('services.api.main.connect', return_value=db), patch('services.api.main.history_version', side_effect=changed):
                with self.assertRaises(MigrationHistoryError):
                    initialize(path)
            self.assertEqual(len(calls), 2); self.assertIn('BEGIN IMMEDIATE', statements)
            self.assertFalse(any(s.startswith(('CREATE', 'INSERT', 'ALTER')) for s in statements), statements)

    def test_failed_legacy_upgrade_rolls_back_without_recording_new_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.sqlite3'; initialize(path)
            for table in ('research_runs', 'auth_users', 'auth_sessions', 'auth_limits', 'gate_runs', 'knowledge_runs', 'agent_runs', 'security_audit'):
                self.execute(path, 'DROP TABLE ' + table)
            self.execute(path, 'DELETE FROM schema_migrations WHERE version>=3')
            before = self.dump(path)
            db = sqlite3.connect(path)
            db.set_authorizer(lambda action, arg1, arg2, database, trigger:
                sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TABLE and arg1 == 'auth_users' else sqlite3.SQLITE_OK)
            with patch('services.api.main.connect', return_value=db):
                with self.assertRaises(sqlite3.DatabaseError):
                    initialize(path)
            self.assertEqual(before, self.dump(path))

    def test_lifespan_failure_does_not_recover_jobs_or_start_workers_and_monitor(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.sqlite3'; initialize(path)
            self.execute(path, 'DELETE FROM schema_migrations WHERE version=4')
            before = self.dump(path)
            with patch('agents.store.AgentStore.recover') as recover, patch('agents.jobs.JobWorker.start') as worker, patch('services.api.monitoring.Monitor.start') as monitor:
                with self.assertRaises(MigrationHistoryError):
                    with TestClient(create_app(path)):
                        self.fail('startup must not admit requests')
                recover.assert_not_called(); worker.assert_not_called(); monitor.assert_not_called()
            self.assertEqual(before, self.dump(path))

    def test_readiness_and_status_reject_history_gap_after_startup_and_recover_after_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.sqlite3'
            with TestClient(create_app(path)) as client:
                app = client.app
                app.state.auth_store.create_user('synthetic-admin', 'synthetic-fixture-password', 'admin')
                login = client.post('/api/v1/auth/login', json={'username':'synthetic-admin','password':'synthetic-fixture-password'}, headers={'Origin':'http://127.0.0.1:8080'})
                self.assertEqual(login.status_code, 200)
                self.assertEqual(client.get('/health/ready').status_code, 200)
                self.execute(path, 'DELETE FROM schema_migrations WHERE version=4')
                self.assertEqual(client.get('/health/live').status_code, 200)
                self.assertEqual(client.get('/health/ready').status_code, 503)
                status = client.get('/api/v1/status')
                self.assertEqual(status.status_code, 503); self.assertEqual(status.json(), {'error':'database_unavailable'})
                with patch('rag.ollama.models', return_value=[]):
                    platform = client.get('/api/v1/research/platform-status').json()
                self.assertFalse(platform['database_ready']); self.assertIsNone(platform['schema_version'])
                self.assertFalse(platform['production_ready'])
                self.execute(path, 'INSERT INTO schema_migrations(version) VALUES (4)')
                self.assertEqual(client.get('/health/ready').status_code, 200)
                self.assertEqual(client.get('/api/v1/status').status_code, 200)

    def test_empty_history_requires_bootstrap_permission_and_read_checks_never_upgrade(self):
        with closing(sqlite3.connect(':memory:')) as db:
            self.assertEqual(history_version(db, 7, allow_empty=True), 0)
            with self.assertRaises(MigrationHistoryError):
                require_current(db, 7)
            db.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT)')
            for version in range(1, 4):
                db.execute('INSERT INTO schema_migrations(version) VALUES (?)', (version,))
            with self.assertRaisesRegex(MigrationHistoryError, 'upgrade_required'):
                require_current(db, 7)
            self.assertEqual(history_version(db, 7), 3)
