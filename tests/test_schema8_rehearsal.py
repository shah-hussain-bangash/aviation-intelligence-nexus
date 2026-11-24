import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from infra.verify_schema8 import FIXTURE, FIXTURE_SHA256, run_rehearsal


class Schema8RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.env = {k:v for k,v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
        self.environment = patch.dict(os.environ, self.env, clear=True); self.environment.start()
        self.folder = tempfile.TemporaryDirectory(); self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup(); self.environment.stop()

    def test_complete_rehearsal_is_synthetic_and_preserves_return_points(self):
        directory = self.root / 'case'
        with patch('infra.releases.docker', side_effect=AssertionError('must not call Docker')):
            report = run_rehearsal(directory)
        self.assertTrue(report['passed'], report)
        self.assertTrue(all(report['checks'].values()))
        self.assertEqual(report['fixture']['canonical_sql_sha256'], FIXTURE_SHA256)
        self.assertFalse(report['primary_state_accessed']); self.assertFalse(report['image_or_container_started'])
        self.assertFalse(report['production_ready']); self.assertFalse(report['real_prediction_or_rag_parity_measured'])
        self.assertFalse(report['post_upgrade_events_in_schema7_return_point'])
        self.assertEqual(json.loads((directory / 'report.json').read_text(encoding='utf-8')), report)
        self.assertTrue((directory / 'schema7-before.sqlite3').is_file())
        self.assertTrue((directory / 'schema8-backup/manifest.json').is_file())
        self.assertNotIn(str(directory), json.dumps(report))

    def test_changed_fixture_is_refused_before_creating_case(self):
        changed = self.root / 'changed.sql'; changed.write_text(FIXTURE.read_text(encoding='utf-8') + '-- changed\n', encoding='utf-8')
        directory = self.root / 'must-not-exist'
        with patch('infra.verify_schema8.FIXTURE', changed):
            with self.assertRaisesRegex(ValueError, 'fixture_not_verified'):
                run_rehearsal(directory)
        self.assertFalse(directory.exists())

    def test_existing_case_is_never_overwritten(self):
        directory = self.root / 'existing'; directory.mkdir(); marker = directory / 'keep.txt'; marker.write_text('previous')
        with self.assertRaises(FileExistsError):run_rehearsal(directory)
        self.assertEqual(marker.read_text(), 'previous'); self.assertEqual(list(directory.iterdir()), [marker])

    def test_runtime_environment_is_refused_before_creating_case(self):
        for key in ('AIN_AGENT_JOBS','AIN_MONITOR_ENABLED','AIN_CONTAINER'):
            with self.subTest(key=key), patch.dict(os.environ, {key:'1'}):
                directory = self.root / 'must-not-exist'
                with self.assertRaises(ValueError):run_rehearsal(directory)
                self.assertFalse(directory.exists())

    def test_failed_recovery_retains_private_case_and_safe_failure_report(self):
        directory = self.root / 'failed'
        with patch('infra.verify_schema8.restore', side_effect=OSError('PRIVATE-DETAIL-PATH')):
            report = run_rehearsal(directory)
        self.assertFalse(report['passed']); self.assertEqual(report['failed_stage'], 'schema8_recovery')
        self.assertNotIn('PRIVATE-DETAIL-PATH', json.dumps(report))
        self.assertTrue((directory / 'schema7-before.sqlite3').exists())
        self.assertTrue((directory / 'schema8-backup/manifest.json').exists())
        self.assertTrue((directory / 'report.json').exists())

    def test_changed_source_cannot_receive_a_passing_report(self):
        from infra.verify_schema8 import source_hashes
        original = source_hashes()
        with patch('infra.verify_schema8.source_hashes', side_effect=[original, {}]):
            report = run_rehearsal(self.root / 'changed-source')
        self.assertFalse(report['passed']); self.assertEqual(report['failed_stage'], 'source_binding')
        self.assertFalse(report['checks']['source_unchanged_during_rehearsal'])

    def test_real_cli_creates_a_new_case_without_accepting_a_live_database_argument(self):
        result = subprocess.run([sys.executable, '-m', 'infra.verify_schema8'], env=self.env, capture_output=True, text=True, timeout=40)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout); self.assertTrue(report['passed'])
        self.assertRegex(report['case_id'], '^[0-9a-f]{32}$')
        denied = subprocess.run([sys.executable, '-m', 'infra.verify_schema8', '--database', 'PRIVATE-LIVE-STATE'], env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(denied.returncode, 2)
