"""Admission does not deserialize or read the source flight database."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from infra import research_model_recovery as recovery


class ResearchModelRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.snapshot = self.root / 'snapshot'
        model = self.snapshot / 'models/delay-v2'; model.mkdir(parents=True)
        (model / 'model.joblib').write_bytes(b'NEVER DESERIALIZE THIS TEST FIXTURE')
        metadata = {'artifact_sha256': recovery.checksum(model / 'model.joblib'), 'model_version': 'delay-v2',
                    'release_assessment': {'research_gate_passed': True}}
        (model / 'report.json').write_text(json.dumps(metadata))
        self.record = {'format': 'ain-recovery-v1', 'snapshot_id': str(uuid4()),
                       'database': {'schema_version': 7}, 'files': [
                           {'path': name, 'size_bytes': (self.snapshot / name).stat().st_size,
                            'sha256': recovery.checksum(self.snapshot / name)}
                           for name in (recovery.MODEL, recovery.REPORT)]}
        self.pin = self.manifest()

    def tearDown(self):
        self.temporary.cleanup()

    def manifest(self):
        path = self.snapshot / 'manifest.json'; path.write_text(json.dumps(self.record))
        return recovery.checksum(path)

    def admit(self, pin=None):
        return recovery.admit(self.snapshot, pin or self.pin, trusted_local_model=True)

    def test_explicit_trust_is_required_before_file_access(self):
        with patch.object(recovery, 'ordinary') as reader, self.assertRaisesRegex(ValueError, 'trusted_local'):
            recovery.admit(self.snapshot, self.pin)
        reader.assert_not_called()

    def test_pinned_pair_is_admitted_without_opening_or_requiring_database(self):
        # The original snapshot's database deliberately does not exist.
        record, files = self.admit()
        self.assertEqual(record['snapshot_id'], self.record['snapshot_id'])
        self.assertEqual(set(files), {recovery.MODEL, recovery.REPORT})
        self.assertFalse((self.snapshot / 'ain.sqlite3').exists())

    def test_manifest_and_artifact_edits_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'manifest_pin'):
            self.admit('0' * 64)
        (self.snapshot / recovery.MODEL).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'artifact_pin'):
            self.admit()

    def test_duplicate_and_traversal_inventory_are_refused(self):
        original = list(self.record['files'])
        for entries in (original + [original[0]], original + [{'path': '../outside', 'size_bytes': 1, 'sha256': '0' * 64}]):
            self.record['files'] = entries; pin = self.manifest()
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError, 'inventory'):
                self.admit(pin)

    def test_duplicate_json_keys_are_refused(self):
        path = self.snapshot / 'manifest.json'
        path.write_text('{"format":"ain-recovery-v1","format":"altered"}')
        with self.assertRaisesRegex(ValueError, 'duplicate_json_key'):
            self.admit(recovery.checksum(path))

    def test_missing_pair_and_failed_research_gate_are_refused(self):
        self.record['files'] = self.record['files'][:1]
        with self.assertRaisesRegex(ValueError, 'model_pair'):
            self.admit(self.manifest())
        self.record['files'].append({'path': recovery.REPORT, 'size_bytes': 1, 'sha256': '0' * 64})
        metadata = {'artifact_sha256': recovery.checksum(self.snapshot / recovery.MODEL), 'model_version': 'delay-v2',
                    'release_assessment': {'research_gate_passed': False}}
        p = self.snapshot / recovery.REPORT; p.write_text(json.dumps(metadata))
        self.record['files'][-1].update(size_bytes=p.stat().st_size, sha256=recovery.checksum(p))
        with self.assertRaisesRegex(ValueError, 'research_model_gate'):
            self.admit(self.manifest())

    def test_worker_failure_is_generic_and_source_pair_remains_unchanged(self):
        before = {p: recovery.checksum(self.snapshot / p) for p in (recovery.MODEL, recovery.REPORT)}
        with patch.object(recovery, 'ROOT', self.root), patch.object(recovery.subprocess, 'run',
             return_value=subprocess.CompletedProcess([], 1, '', 'PRIVATE FAILURE CONTENT')), redirect_stdout(io.StringIO()):
            report, path = recovery.run_check(self.snapshot, self.pin, trusted_local_model=True)
        self.assertFalse(report['passed'])
        self.assertEqual(report['error'], 'research_model_recovery_unverified')
        self.assertNotIn('PRIVATE FAILURE CONTENT', path.read_text())
        self.assertEqual(before, {p: recovery.checksum(self.snapshot / p) for p in before})

    def test_isolated_worker_executes_fitted_synthetic_model_and_restore(self):
        import joblib
        import pandas as pd
        from ml.train_v2 import build_model, PROTOCOL_PATH
        from threadpoolctl import threadpool_limits
        model = build_model(15, json.loads(PROTOCOL_PATH.read_text()))
        frame = pd.DataFrame({'carrier': ['AA'] * 500, 'origin': ['JFK'] * 500,
                              'destination': ['LAX'] * 500, 'scheduled_departure_hour': ['9'] * 500,
                              'scheduled_departure_minute': ['0'] * 500, 'day_of_week': ['1'] * 500})
        with threadpool_limits(limits=2): model.fit(frame, [0, 1] * 250)
        base = recovery.ROOT / '.local/research-model-recovery'; base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            case = Path(directory).resolve()
            self.assertEqual(case.parent, base.resolve())
            state = case / 'state'; model_dir = state / 'models/delay-v2'; model_dir.mkdir(parents=True)
            joblib.dump(model, model_dir / 'model.joblib')
            (model_dir / 'report.json').write_text(json.dumps({
                'artifact_sha256': recovery.checksum(model_dir / 'model.joblib'), 'model_version': 'delay-v2',
                'release_assessment': {'research_gate_passed': True}}))
            (case / 'plan.json').write_text(json.dumps({'files': {
                name: {'sha256': recovery.checksum(state / name)} for name in (recovery.MODEL, recovery.REPORT)}}))
            env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
            env.update(AIN_ENV='test', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0',
                       AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'))
            worker = 'import json,sys;from infra.research_model_recovery import execute_case;print(json.dumps(execute_case(sys.argv[1])))'
            result = subprocess.run([sys.executable, '-c', worker, str(case)], cwd=recovery.ROOT, env=env,
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report['passed'])
            self.assertTrue(all(report['checks'].values()))
            self.assertEqual(len(report['prediction_results']), 3)
            self.assertTrue(all(abs(row['arrival_delay_15_probability'] - .5) < 1e-10
                                for row in report['prediction_results']))
            self.assertEqual(report['restoration']['session_revocation_event_id'],
                             report['offline_consistency']['session_revocation_event_id'])
            self.assertFalse(report['model_retrained'])


if __name__ == '__main__':
    unittest.main()
