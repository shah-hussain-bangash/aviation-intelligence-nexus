"""Small synthetic schema-7 fixtures only; no real records or Docker required."""
from contextlib import closing, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from infra import full_snapshot_recovery as recovery
from infra.verify_schema8 import seed_fixture, fixture_text


class FullSnapshotRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.root = Path(self.temporary.name)
        self.snapshot = self.root / 'snapshot'
        seed_fixture(self.snapshot, fixture_text(), 'synthetic-offline-password-123', 'synthetic-session-token', str(uuid4()))
        self.pin = self.manifest()

    def tearDown(self): self.temporary.cleanup()

    def manifest(self):
        with closing(sqlite3.connect((self.snapshot / 'ain.sqlite3').as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            counts = {t: db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
                      for t in recovery.SNAPSHOT_TABLES if t != 'security_audit'}
        self.record = {'format': 'ain-recovery-v1', 'snapshot_id': str(uuid4()),
                       'database': {'schema_version': 7, 'row_counts': counts}, 'files': [
                           {'path': name, 'size_bytes': (self.snapshot / name).stat().st_size,
                            'sha256': recovery.checksum(self.snapshot / name)} for name in recovery.FILES]}
        path = self.snapshot / 'manifest.json'; path.write_text(json.dumps(self.record))
        return recovery.checksum(path)

    def test_offline_acknowledgement_precedes_all_file_reads(self):
        with patch.object(recovery, 'ordinary') as read, self.assertRaisesRegex(ValueError, 'acknowledgement'):
            recovery.admit(self.snapshot, self.pin)
        read.assert_not_called()

    def test_valid_full_fixture_and_changed_pins(self):
        _, inventory = recovery.admit(self.snapshot, self.pin, offline_snapshot=True)
        self.assertEqual(set(inventory), set(recovery.FILES))
        with self.assertRaisesRegex(ValueError, 'manifest_pin'):
            recovery.admit(self.snapshot, '0' * 64, offline_snapshot=True)
        with (self.snapshot / 'ain.sqlite3').open('ab') as stream: stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'file_mismatch'):
            recovery.admit(self.snapshot, self.pin, offline_snapshot=True)

    def test_even_empty_sqlite_sidecars_are_refused(self):
        for suffix in ('-wal', '-shm', '-journal'):
            path = Path(str(self.snapshot / 'ain.sqlite3') + suffix); path.touch()
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, 'sidecar'):
                recovery.admit(self.snapshot, self.pin, offline_snapshot=True)
            path.unlink()

    def test_incomplete_count_inventory_and_future_schema_are_refused(self):
        self.record['database']['row_counts'].pop('flights')
        path = self.snapshot / 'manifest.json'; path.write_text(json.dumps(self.record))
        with self.assertRaisesRegex(ValueError, 'count_inventory'):
            recovery.admit(self.snapshot, recovery.checksum(path), offline_snapshot=True)
        self.record['database']['schema_version'] = 99; path.write_text(json.dumps(self.record))
        with self.assertRaisesRegex(ValueError, 'schema_invalid'):
            recovery.admit(self.snapshot, recovery.checksum(path), offline_snapshot=True)

    def test_insufficient_disk_is_refused_before_creating_a_case(self):
        with patch.object(recovery, 'ROOT', self.root), patch.object(recovery.shutil, 'disk_usage',
             return_value=type('Usage', (), {'free': 0})()), self.assertRaisesRegex(ValueError, 'disk_budget'):
            recovery.run_check(self.snapshot, self.pin, offline_snapshot=True)
        self.assertFalse((self.root / '.local').exists())

    def test_failed_worker_is_generic_and_source_bytes_remain_unchanged(self):
        before = {n: recovery.checksum(self.snapshot / n) for n in recovery.FILES}
        with patch.object(recovery, 'ROOT', self.root), patch.object(recovery.subprocess, 'run',
             return_value=subprocess.CompletedProcess([], 1, '', 'PRIVATE ROW CONTENT')), redirect_stdout(io.StringIO()):
            report, path = recovery.run_check(self.snapshot, self.pin, offline_snapshot=True)
        self.assertFalse(report['passed']); self.assertNotIn('PRIVATE ROW CONTENT', path.read_text())
        self.assertEqual(before, {n: recovery.checksum(self.snapshot / n) for n in before})

    def worker(self, *, active_agent=False):
        if active_agent:
            with closing(sqlite3.connect(self.snapshot / 'ain.sqlite3')) as db, db:
                db.execute('INSERT INTO agent_runs VALUES(?,?,?,?,?,?)',
                           ('fixture-agent', 'fixture-owner', 'fixture-key', 'a' * 64,
                            '{"state":"running"}', '2025-01-01T00:00:00+00:00'))
            self.pin = self.manifest()
        base = recovery.ROOT / '.local/full-snapshot-recovery'; base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            case = Path(directory).resolve(); self.assertEqual(case.parent, base.resolve())
            state = case / 'state'; state.mkdir()
            for name in recovery.FILES:
                target = state / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.snapshot / name, target)
            (case / 'plan.json').write_text(json.dumps({'files': {e['path']: e for e in self.record['files']},
                                                      'database': self.record['database']}))
            env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
            env.update(AIN_ENV='test', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0',
                       AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'))
            code = 'import json,sys;from infra.full_snapshot_recovery import execute_case;print(json.dumps(execute_case(sys.argv[1])))'
            return subprocess.run([sys.executable, '-c', code, str(case)], cwd=recovery.ROOT, env=env,
                                  capture_output=True, text=True, timeout=120)

    def test_real_worker_upgrade_restore_preserves_rows_and_artifacts(self):
        before = recovery.checksum(self.snapshot / 'ain.sqlite3')
        result = self.worker(); self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['passed']); self.assertTrue(all(report['checks'].values()))
        self.assertEqual(report['input_schema_version'], 7); self.assertEqual(report['restored_schema_version'], 8)
        self.assertEqual(report['flight_records'], 1)
        self.assertEqual(report['restored_table_fingerprints']['auth_users'], report['table_fingerprints_before_upgrade']['auth_users'])
        self.assertEqual(report['restored_table_fingerprints']['auth_sessions']['rows'], 0)
        self.assertEqual(report['restoration']['session_revocation_event_id'], report['offline_consistency']['session_revocation_event_id'])
        self.assertEqual(before, recovery.checksum(self.snapshot / 'ain.sqlite3'))

    def test_active_agent_snapshot_is_refused(self):
        result = self.worker(active_agent=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('nonquiescent_agent_snapshot', result.stderr)


if __name__ == '__main__': unittest.main()
