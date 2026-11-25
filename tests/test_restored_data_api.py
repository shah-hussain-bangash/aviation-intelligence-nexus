"""Disposable restored-data fixture and real loopback gateway/API; no Docker."""
from contextlib import closing, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from infra import restored_data_api as probe
from infra import full_snapshot_recovery as recovery
from infra.verify_schema8 import seed_fixture, fixture_text, source_identity


def remove_owned(path, parent):
    path = Path(path).resolve(); parent = Path(parent).resolve()
    if path.parent != parent: raise AssertionError('Unexpected test cleanup path')
    shutil.rmtree(path)


def free_ports():
    with socket.socket() as first, socket.socket() as second:
        first.bind(('127.0.0.1', 0)); second.bind(('127.0.0.1', 0))
        return first.getsockname()[1], second.getsockname()[1]


class RestoredDataApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = probe.ROOT / '.local/full-snapshot-recovery'; base.mkdir(parents=True, exist_ok=True)
        cls.case = base / uuid4().hex; cls.case.mkdir()
        cls.addClassCleanup(remove_owned, cls.case, base)
        state = cls.case / 'state'
        seed_fixture(state, fixture_text(), 'synthetic-restored-password-123', 'synthetic-old-token', str(uuid4()))
        with closing(sqlite3.connect(state / 'ain.sqlite3')) as db, db:
            db.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination,cancelled,diverted) VALUES('BTS_REPORTING_CARRIER','test-1','2025-01-01','AA','JFK','LAX',0,0)")
            counts = {t: db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in recovery.SNAPSHOT_TABLES if t != 'security_audit'}
        if hasattr(cls, 'configure_model'): cls.configure_model(state)
        files = {name: {'sha256': recovery.checksum(state / name), 'size_bytes': (state / name).stat().st_size}
                 for name in recovery.FILES}
        (cls.case / 'plan.json').write_text(json.dumps({'files': files, 'database': {'schema_version': 7, 'row_counts': counts}}))
        env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
        env.update(AIN_ENV='test', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0',
                   AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'))
        code = 'import json,sys;from infra.full_snapshot_recovery import execute_case;print(json.dumps(execute_case(sys.argv[1])))'
        result = subprocess.run([sys.executable, '-c', code, str(cls.case)], cwd=probe.ROOT, env=env,
                                capture_output=True, text=True, timeout=120)
        if result.returncode: raise AssertionError(result.stderr)
        outcome = json.loads(result.stdout)
        cls.revision = 'a' * 40
        identity = source_identity()
        # Synthetic report metadata for admission tests, not a release attestation.
        identity.update(source_revision=cls.revision, working_tree_changes=False)
        cls.record = {'format': 'ain-full-snapshot-recovery-v1', **outcome, 'production_ready': False,
                      'primary_state_accessed': False, 'source_snapshot_migrated': False,
                      'toolkit_identity': identity, 'verifier_sha256': probe.checksum(probe.ROOT / 'infra/full_snapshot_recovery.py')}
        cls.report = cls.case / 'report.json'
        cls.raw = json.dumps(cls.record).encode(); cls.report.write_bytes(cls.raw)
        cls.pin = probe.checksum(cls.report)

    def tearDown(self): self.report.write_bytes(self.raw)

    def test_admission_binds_qualified_case_and_selected_contracts(self):
        record, source, files = probe.admit(self.report, self.pin, self.revision)
        self.assertEqual(record['flight_records'], 2)
        self.assertEqual(source, self.case / 'restored')
        self.assertEqual(set(files), set(recovery.FILES))

    def test_report_pin_and_recovery_revision_mismatches_are_refused(self):
        for pin, revision in [('0' * 64, self.revision), (self.pin, 'b' * 40)]:
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                probe.admit(self.report, pin, revision)

    def test_primary_scope_and_changed_contracts_are_refused(self):
        for change in ('scope', 'contract'):
            record = json.loads(self.raw)
            if change == 'scope': record['primary_state_accessed'] = True
            else: record['toolkit_identity']['source_sha256']['services/api/auth.py'] = '0' * 64
            self.report.write_text(json.dumps(record))
            with self.subTest(change=change), self.assertRaises(ValueError):
                probe.admit(self.report, probe.checksum(self.report), self.revision)

    def test_changed_qualified_database_is_refused(self):
        db = self.case / 'restored/ain.sqlite3'; original = db.read_bytes()
        try:
            db.write_bytes(original + b'changed')
            with self.assertRaisesRegex(ValueError, 'qualified_restored_file_changed'):
                probe.admit(self.report, self.pin, self.revision)
        finally: db.write_bytes(original)

    def test_invalid_ports_are_refused_before_report_access(self):
        with patch.object(probe, 'admit') as read:
            for web, api in [(80, 18102), (18180, 18180), (True, 18102)]:
                with self.subTest(web=web, api=api), self.assertRaises(ValueError):
                    probe.run_check(self.report, self.pin, self.revision, web_port=web, api_port=api)
            read.assert_not_called()

    def test_timeout_cleanup_targets_only_owned_process_handle(self):
        process = Mock(); process.poll.side_effect = [None, 0]
        process.wait.side_effect = [subprocess.TimeoutExpired('owned-test', 10), 0]
        probe.stop_owned(process)
        process.terminate.assert_called_once(); process.kill.assert_called_once()

    def test_failed_prepare_starts_no_services_and_preserves_qualified_source(self):
        original = probe.checksum(self.case / 'restored/ain.sqlite3')
        web, api = free_ports()
        with (patch.object(probe.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'PRIVATE FAILURE')),
              redirect_stdout(io.StringIO())):
            record, target = probe.run_check(self.report, self.pin, self.revision, web_port=web, api_port=api)
        self.addCleanup(remove_owned, target.parent, probe.ROOT / '.local/restored-api')
        self.assertFalse(record['passed']); self.assertTrue(record['owned_services_stopped'])
        self.assertNotIn('PRIVATE FAILURE', target.read_text())
        self.assertEqual(original, probe.checksum(self.case / 'restored/ain.sqlite3'))

    def test_actual_gateway_api_login_roles_summary_and_cleanup_on_copy(self):
        web, api = free_ports()
        original = probe.checksum(self.case / 'restored/ain.sqlite3')
        with redirect_stdout(io.StringIO()):
            record, target = probe.run_check(self.report, self.pin, self.revision, web_port=web, api_port=api)
        self.addCleanup(remove_owned, target.parent, probe.ROOT / '.local/restored-api')
        self.assertTrue(record['passed'], record)
        self.assertTrue(record['owned_services_stopped'])
        self.assertTrue(all(record['checks'].values()))
        self.assertEqual(record['dataset_records'], 1)  # Synthetic source row is excluded.
        self.assertTrue(record['copy_state_checks']['original_accounts_preserved'])
        self.assertEqual(original, probe.checksum(self.case / 'restored/ain.sqlite3'))
        for port in (web, api):
            with socket.socket() as socket_probe:
                self.assertNotEqual(socket_probe.connect_ex(('127.0.0.1', port)), 0)


if __name__ == '__main__': unittest.main()
