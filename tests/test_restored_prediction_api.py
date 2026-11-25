"""Synthetic fitted model; real proxy/API persistence and owned restart."""
from contextlib import closing, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from tests import test_restored_data_api as fixture
from infra import restored_data_api as probe


class RestoredPredictionApiTests(unittest.TestCase):
    @classmethod
    def configure_model(cls, state):
        import joblib
        import pandas as pd
        from threadpoolctl import threadpool_limits
        from ml.train_v2 import build_model, PROTOCOL_PATH
        model = build_model(15, json.loads(PROTOCOL_PATH.read_text()))
        frame = pd.DataFrame({'carrier': ['AA'] * 500, 'origin': ['JFK'] * 500,
                              'destination': ['LAX'] * 500, 'scheduled_departure_hour': ['9'] * 500,
                              'scheduled_departure_minute': ['0'] * 500, 'day_of_week': ['1'] * 500})
        with threadpool_limits(limits=2): model.fit(frame, [0, 1] * 250)
        directory = state / 'models/delay-v2'
        joblib.dump(model, directory / 'model.joblib')
        (directory / 'report.json').write_text(json.dumps({'artifact_sha256': probe.checksum(directory / 'model.joblib'),
            'model_version': 'delay-v2', 'release_assessment': {'research_gate_passed': True}}))

    @classmethod
    def setUpClass(cls): fixture.RestoredDataApiTests.setUpClass.__func__(cls)

    def tearDown(self): self.report.write_bytes(self.raw)

    def test_prediction_requires_explicit_trust_before_report_access(self):
        with patch.object(probe, 'admit') as read, self.assertRaisesRegex(ValueError, 'trusted_local_model'):
            probe.run_check(self.report, self.pin, self.revision, with_prediction=True)
        read.assert_not_called()

    def test_cli_prediction_without_trust_is_refused(self):
        result = subprocess.run([sys.executable, '-m', 'infra.restored_data_api', '--recovery-report', str(self.report),
                                 '--report-sha256', self.pin, '--expected-recovery-revision', self.revision,
                                 '--with-prediction'], cwd=probe.ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['error'], 'restored_data_api_admission_refused')

    def test_missing_model_pair_is_refused_before_starting_services(self):
        record = json.loads(self.raw); record['artifact_sha256'] = {}
        self.report.write_text(json.dumps(record))
        with patch.object(probe.subprocess, 'Popen') as launch, self.assertRaisesRegex(ValueError, 'model_pair'):
            probe.run_check(self.report, probe.checksum(self.report), self.revision,
                            with_prediction=True, trusted_local_model=True)
        launch.assert_not_called()

    def test_changed_qualified_model_is_not_deserialized(self):
        artifact = self.case / 'restored/models/delay-v2/model.joblib'; original = artifact.read_bytes()
        try:
            artifact.write_bytes(original + b'changed')
            with patch.object(probe.subprocess, 'Popen') as launch, self.assertRaisesRegex(ValueError, 'qualified_restored_file_changed'):
                probe.run_check(self.report, self.pin, self.revision, with_prediction=True, trusted_local_model=True)
            launch.assert_not_called()
        finally: artifact.write_bytes(original)

    def inspect_worker(self, case):
        state = case / 'state'
        env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
        env.update(AIN_ENV='test', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0',
                   AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'))
        code = 'import json,sys;from infra.restored_data_api import inspect_after;print(json.dumps(inspect_after(sys.argv[1])))'
        return subprocess.run([sys.executable, '-c', code, str(case)], cwd=probe.ROOT, env=env,
                              capture_output=True, text=True, timeout=120)

    def test_prediction_replay_conflict_restart_and_history_isolation(self):
        web, api = fixture.free_ports()
        source_pin = probe.checksum(self.case / 'restored/ain.sqlite3')
        with redirect_stdout(io.StringIO()):
            report, target = probe.run_check(self.report, self.pin, self.revision, web_port=web, api_port=api,
                                             with_prediction=True, trusted_local_model=True)
        self.addCleanup(fixture.remove_owned, target.parent, probe.ROOT / '.local/restored-api')
        self.assertTrue(report['passed'], report)
        self.assertTrue(report['owned_services_stopped'])
        self.assertTrue(all(report['prediction_checks'].values()))
        self.assertTrue(report['prediction']['owned_api_restart_exercised'])
        self.assertAlmostEqual(report['prediction']['probability'], .5)
        self.assertTrue(report['prediction']['research_only'])
        self.assertFalse(report['prediction']['operational_serving_approved'])
        self.assertFalse(report['model_retrained']); self.assertFalse(report['model_accuracy_evaluated'])
        self.assertTrue(report['copy_state_checks']['one_bound_probe_prediction_only'])
        self.assertEqual(probe.checksum(self.case / 'restored/ain.sqlite3'), source_pin)
        database = target.parent / 'state/ain.sqlite3'
        with closing(sqlite3.connect(database)) as db, db:
            original = db.execute('SELECT id,result_json FROM research_runs WHERE id!=?', (report['prediction']['run_id'],)).fetchone()
            db.execute('UPDATE research_runs SET result_json=? WHERE id=?', ('{"altered":true}', original[0]))
        corrupted = self.inspect_worker(target.parent)
        self.assertNotEqual(corrupted.returncode, 0)
        self.assertIn('original_research_rows_changed', corrupted.stderr)
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('UPDATE research_runs SET result_json=? WHERE id=?', (original[1], original[0]))
            row = db.execute('SELECT * FROM research_runs WHERE id=?', (report['prediction']['run_id'],)).fetchone()
            db.execute('INSERT INTO research_runs VALUES(?,?,?,?,?,?,?,?,?)', (str(uuid4()), str(uuid4()), *row[2:]))
        duplicated = self.inspect_worker(target.parent)
        self.assertNotEqual(duplicated.returncode, 0)
        self.assertIn('probe_prediction_count_unexpected', duplicated.stderr)


if __name__ == '__main__': unittest.main()
