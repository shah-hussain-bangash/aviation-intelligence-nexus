import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from infra.schema_preflight import inspect_snapshot, VERSION
from services.api.main import initialize
from services.api.paths import SCHEMA_VERSION


class SchemaPreflightTests(unittest.TestCase):
    def fixture(self, folder):
        path = Path(folder) / 'synthetic.sqlite3'
        initialize(path)
        with closing(sqlite3.connect(path)) as db:
            db.execute("INSERT INTO auth_users VALUES ('synthetic','PRIVATE-USER','PRIVATE-HASH','viewer',1)")
            db.commit()
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        return path

    def check(self, path):
        return inspect_snapshot(path, offline_snapshot=True)

    def mutate(self, path, sql):
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(sql)

    def test_current_schema_checks_without_byte_or_directory_changes(self):
        self.assertEqual(VERSION, SCHEMA_VERSION)
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder)
            before = path.read_bytes(); entries = set(Path(folder).iterdir())
            report = self.check(path)
            self.assertTrue(report['local_schema_checks_passed'], report)
            self.assertEqual(report['snapshot_sha256'], hashlib.sha256(before).hexdigest())
            self.assertEqual(before, path.read_bytes()); self.assertEqual(entries, set(Path(folder).iterdir()))
            self.assertFalse(report['migration_performed']); self.assertFalse(report['production_ready'])
            for private in ('PRIVATE-USER', 'PRIVATE-HASH', folder):
                self.assertNotIn(private, json.dumps(report))

    def test_no_acknowledgement_never_opens_or_creates_database(self):
        with tempfile.TemporaryDirectory() as folder, patch('sqlite3.connect', side_effect=AssertionError('must not open')):
            path = Path(folder) / 'missing.sqlite3'
            self.assertEqual(inspect_snapshot(path)['errors'], ['offline_snapshot_acknowledgement_required'])
            self.assertFalse(path.exists())

    def test_sidecars_refused_before_open_and_missing_file_not_created(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder)
            for suffix in ('-wal', '-shm', '-journal'):
                sidecar = Path(str(path) + suffix); sidecar.write_bytes(b'synthetic')
                with patch('sqlite3.connect', side_effect=AssertionError('must not open')):
                    self.assertEqual(self.check(path)['errors'], ['sqlite_sidecar_present'])
                sidecar.unlink()
            missing = path.parent / 'missing.sqlite3'
            self.assertFalse(self.check(missing)['local_schema_checks_passed']); self.assertFalse(missing.exists())

    def test_gapped_history_cannot_pass_using_max_version(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder); self.mutate(path, 'DELETE FROM schema_migrations WHERE version=4')
            self.assertEqual(self.check(path)['errors'], ['migration_history_gap'])

    def test_old_and_new_versions_are_not_automatically_migrated(self):
        for sql, code, status in [
            ('DELETE FROM schema_migrations WHERE version=7', 'schema_upgrade_requires_separate_review', 'migration_required'),
            ('INSERT INTO schema_migrations(version) VALUES (8)', 'schema_newer_than_service', 'blocked')]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as folder:
                path = self.fixture(folder); self.mutate(path, sql); before = path.read_bytes()
                report = self.check(path)
                self.assertEqual(report['errors'], [code]); self.assertEqual(report['status'], status)
                self.assertEqual(before, path.read_bytes())

    def test_missing_table_column_index_and_uniqueness_block(self):
        cases = [
            ('DROP TABLE imports', 'required_table_missing'),
            ('ALTER TABLE flights DROP COLUMN cancelled', 'required_column_missing'),
            ('DROP INDEX research_runs_owner', 'required_index_missing'),
            ('CREATE TABLE gate_runs(id TEXT PRIMARY KEY,owner_id TEXT,request_key TEXT,scenario_hash TEXT,result_json TEXT,created_at TEXT)', 'required_uniqueness_missing')]
        for sql, code in cases:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as folder:
                path = self.fixture(folder)
                if code == 'required_uniqueness_missing':
                    self.mutate(path, 'DROP TABLE gate_runs'); self.mutate(path, sql)
                    self.mutate(path, 'CREATE INDEX gate_runs_owner ON gate_runs(owner_id,created_at)')
                else:
                    self.mutate(path, sql)
                self.assertEqual(self.check(path)['errors'], [code])

    def test_corrupt_oversize_changed_and_budget_exhausted_are_safe_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder)
            with patch('infra.schema_preflight.MAX_BYTES', 1):
                self.assertEqual(self.check(path)['errors'], ['snapshot_size_not_allowed'])
            with patch('infra.schema_preflight.SECONDS', 0):
                self.assertEqual(self.check(path)['errors'], ['inspection_budget_exceeded'])
            original = hashlib.sha256
            counter = [0]
            def changed_digest():
                counter[0] += 1
                return original(b'changed') if counter[0] == 2 else original()
            with patch('infra.schema_preflight.hashlib.sha256', side_effect=changed_digest):
                self.assertEqual(self.check(path)['errors'], ['snapshot_changed'])
            path.write_bytes(b'PRIVATE-CORRUPTION')
            report = self.check(path)
            self.assertFalse(report['local_schema_checks_passed']); self.assertNotIn('PRIVATE', json.dumps(report))

    def test_cli_requires_explicit_snapshot_and_acknowledgement(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.fixture(folder)
            command = [sys.executable, '-m', 'infra.schema_preflight', str(path)]
            denied = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(denied.returncode, 2)
            passed = subprocess.run(command + ['--offline-snapshot'], capture_output=True, text=True, timeout=15)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertTrue(json.loads(passed.stdout)['local_schema_checks_passed'])
