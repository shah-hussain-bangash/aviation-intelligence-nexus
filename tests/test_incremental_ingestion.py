from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pipelines.import_bts import import_archive
from pipelines.synthetic_ingestion import create_case, enqueue, exclusive, jobs, work_one
from pipelines.verify_import_safety import BASE, fixture
from pipelines.verify_incremental_ingestion import verify, state
from services.api.paths import ROOT


class IncrementalIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.case = create_case(self.root/'case')

    def tearDown(self):
        self.temporary.cleanup()

    def enqueue(self):
        return enqueue(self.case, BASE, year=2025, month=1)

    def test_expected_hash_checked_before_database_creation(self):
        archive = self.root/'fixture.zip'; fixture(archive, BASE)
        target = self.root/'missing.sqlite3'
        with self.assertRaisesRegex(ValueError, 'does not match expected identity'):
            import_archive(archive, target, 2025, 1, synthetic=True, expected_sha256='0'*64)
        self.assertFalse(target.exists())
        for invalid in ('abc', True, []):
            with self.assertRaisesRegex(ValueError, 'Invalid expected archive identity'):
                import_archive(archive, target, 2025, 1, synthetic=True, expected_sha256=invalid)
        self.assertFalse(target.exists())
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        result = import_archive(archive, target, 2025, 1, synthetic=True, expected_sha256=digest)
        self.assertEqual(result['sha256'], digest)
        self.assertEqual(result['rows_inserted'], 3)

    def test_commit_before_queue_ack_recovers_without_duplicate_rows(self):
        job = self.enqueue()
        real = import_archive
        def interrupted(*args, **kwargs):
            real(*args, **kwargs)
            raise KeyboardInterrupt()
        with patch('pipelines.synthetic_ingestion.import_archive', interrupted), self.assertRaises(KeyboardInterrupt):
            work_one(self.case)
        self.assertEqual(jobs(self.case)[0]['state'], 'running')
        before = state(self.case)
        resumed = work_one(self.case)
        self.assertEqual(resumed['job_id'], job)
        self.assertEqual(resumed['import_status'], 'already_imported')
        self.assertEqual(resumed['attempts'], 2)
        self.assertEqual(state(self.case), before)
        self.assertIsNone(work_one(self.case))

    def test_live_worker_lock_prevents_claim_or_enqueue(self):
        self.enqueue()
        with exclusive(self.case):
            with self.assertRaisesRegex(ValueError, '^synthetic_worker_busy$'):
                work_one(self.case)
            with self.assertRaisesRegex(ValueError, '^synthetic_worker_busy$'):
                self.enqueue()
        self.assertEqual(jobs(self.case)[0]['attempts'], 0)
        self.assertEqual(work_one(self.case)['state'], 'succeeded')

    def test_changed_archive_quarantined_before_application_database(self):
        job = self.enqueue()
        (self.case/'archives'/(job+'.zip')).write_bytes(b'changed')
        result = work_one(self.case)
        self.assertEqual(result['state'], 'quarantined')
        self.assertFalse((self.case/'flights.sqlite3').exists())
        self.assertIsNone(jobs(self.case)[0]['result_json'])

    def test_live_lock_is_respected_by_a_separate_process(self):
        self.enqueue()
        code = '''import sys
from pipelines.synthetic_ingestion import work_one
try:
    work_one(sys.argv[1])
except ValueError as error:
    raise SystemExit(0 if str(error)=='synthetic_worker_busy' else 4)
raise SystemExit(5)
'''
        with exclusive(self.case):
            result = subprocess.run([sys.executable,'-c',code,str(self.case)],cwd=ROOT,capture_output=True,timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(jobs(self.case)[0]['attempts'], 0)

    def test_busy_retries_bounded_and_nonbusy_database_failure_blocks(self):
        self.enqueue()
        busy = sqlite3.OperationalError('PRIVATE DETAIL'); busy.sqlite_errorcode = sqlite3.SQLITE_BUSY_SNAPSHOT
        with patch('pipelines.synthetic_ingestion.import_archive', side_effect=busy):
            self.assertEqual(work_one(self.case)['state'], 'queued')
            self.assertEqual(work_one(self.case)['state'], 'queued')
            self.assertEqual(work_one(self.case)['reason'], 'attempt_limit')
        self.assertEqual(jobs(self.case)[0]['attempts'], 3)
        self.assertIsNone(work_one(self.case))
        self.enqueue()
        failure = sqlite3.OperationalError('PRIVATE DETAIL'); failure.sqlite_errorcode = sqlite3.SQLITE_IOERR
        with patch('pipelines.synthetic_ingestion.import_archive', side_effect=failure):
            result = work_one(self.case)
        self.assertEqual((result['state'], result['reason']), ('blocked', 'database_unavailable'))
        self.assertNotIn('PRIVATE DETAIL', json.dumps(jobs(self.case)))

    def test_repeated_interrupted_worker_exhausts_attempt_limit(self):
        self.enqueue()
        with patch('pipelines.synthetic_ingestion.import_archive', side_effect=KeyboardInterrupt):
            for _ in range(3):
                with self.assertRaises(KeyboardInterrupt):
                    work_one(self.case)
        self.assertIsNone(work_one(self.case))
        row = jobs(self.case)[0]
        self.assertEqual((row['state'], row['attempts'], row['reason']), ('quarantined', 3, 'attempt_limit'))

    def test_job_row_limits_markers_and_existing_case_are_preserved(self):
        with self.assertRaises(FileExistsError):create_case(self.case)
        with self.assertRaises(ValueError):enqueue(self.case, [], year=2025, month=1)
        with patch('pipelines.synthetic_ingestion.MAX_JOBS', 1):
            self.enqueue()
            with self.assertRaisesRegex(ValueError, '^synthetic_job_limit$'):self.enqueue()
        (self.case/'case.json').write_text('{"format":"unapproved"}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '^synthetic_case_marker_required$'):work_one(self.case)
        with patch.dict(os.environ, {'AIN_AGENT_JOBS':'1'}), self.assertRaises(ValueError):
            create_case(self.root/'refused')
        self.assertFalse((self.root/'refused').exists())

    def test_actual_abrupt_process_exit_and_restarted_incremental_trace(self):
        result = verify(self.root/'verified')
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['checks']), 11)
        self.assertEqual(result['crash_exit_code'], 73)
        self.assertEqual(result['counts'], dict(flights=4, imports=2, observed_bts=0))
        self.assertEqual([row['state'] for row in result['jobs']], ['succeeded','succeeded','quarantined'])
        self.assertFalse(result['primary_database_accessed'])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_actual_cli_and_no_existing_database_argument(self):
        command = [sys.executable, '-m', 'pipelines.verify_incremental_ingestion']
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])
        bad = subprocess.run([*command, '--database', 'PRIVATE_PATH'], cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(bad.returncode, 2)


if __name__ == '__main__':
    unittest.main()
