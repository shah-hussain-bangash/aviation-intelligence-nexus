from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pipelines.synthetic_ingestion import create_case, enqueue, enable_schedule, jobs, pause_schedule, schedule_status, work_one, due_time, MAX_EPOCH
from pipelines.verify_import_safety import BASE
from pipelines.verify_retry_scheduling import busy, verify
from services.api.paths import ROOT


class RetrySchedulingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.case = create_case(self.root/'case')
        enqueue(self.case,BASE,year=2025,month=1)

    def tearDown(self):
        self.temp.cleanup()

    def test_extension_is_opt_in_idempotent_and_does_not_change_legacy_case(self):
        self.assertNotIn('not_before', jobs(self.case)[0])
        with self.assertRaisesRegex(ValueError,'scheduler_not_enabled'):schedule_status(self.case,now=1000)
        self.assertNotIn('not_before', jobs(self.case)[0])
        self.assertTrue(enable_schedule(self.case))
        self.assertFalse(enable_schedule(self.case))
        with self.assertRaisesRegex(ValueError,'configuration_mismatch'):enable_schedule(self.case,base_delay_seconds=10)
        self.assertEqual(jobs(self.case)[0]['not_before'],0)

    def test_busy_due_time_survives_invocations_and_boundary_is_inclusive(self):
        enable_schedule(self.case)
        with patch('pipelines.synthetic_ingestion.import_archive',side_effect=busy()):
            first = work_one(self.case,now=1000)
        self.assertEqual(first['attempts'],1)
        self.assertEqual(jobs(self.case)[0]['not_before'],1030)
        self.assertIsNone(work_one(self.case,now=1029))
        self.assertEqual(jobs(self.case)[0]['attempts'],1)
        result = work_one(self.case,now=1030)
        self.assertEqual((result['state'],result['attempts']),('succeeded',2))
        self.assertEqual(jobs(self.case)[0]['not_before'],0)

    def test_pause_retains_due_work_without_consuming_attempts(self):
        enable_schedule(self.case)
        pause_schedule(self.case,True)
        self.assertEqual(schedule_status(self.case,now=1000)['eligible'],0)
        self.assertIsNone(work_one(self.case,now=1000))
        self.assertEqual(jobs(self.case)[0]['attempts'],0)
        pause_schedule(self.case,False)
        self.assertEqual(schedule_status(self.case,now=1000)['eligible'],1)
        self.assertEqual(work_one(self.case,now=1000)['state'],'succeeded')

    def test_retry_backoff_exhaustion_and_hour_cap(self):
        enable_schedule(self.case)
        with patch('pipelines.synthetic_ingestion.import_archive',side_effect=busy()):
            work_one(self.case,now=1000)
            work_one(self.case,now=1030)
            self.assertEqual(jobs(self.case)[0]['not_before'],1090)
            final = work_one(self.case,now=1090)
        self.assertEqual((final['state'],final['reason']),('quarantined','attempt_limit'))
        other = create_case(self.root/'capped'); enqueue(other,BASE,year=2025,month=1)
        enable_schedule(other,base_delay_seconds=3600)
        with patch('pipelines.synthetic_ingestion.import_archive',side_effect=busy()):
            work_one(other,now=1000); work_one(other,now=4600)
        self.assertEqual(jobs(other)[0]['not_before'],8200)

    def test_interrupted_worker_recovery_defers_once_without_extending_on_idle_ticks(self):
        enable_schedule(self.case)
        with patch('pipelines.synthetic_ingestion.import_archive',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
            work_one(self.case,now=1000)
        self.assertIsNone(work_one(self.case,now=1001))
        self.assertEqual(jobs(self.case)[0]['not_before'],1031)
        self.assertIsNone(work_one(self.case,now=1002))
        self.assertEqual(jobs(self.case)[0]['not_before'],1031)
        self.assertEqual(work_one(self.case,now=1031)['attempts'],2)

    def test_bad_time_pause_delay_or_partial_extension_refused(self):
        for value in (-1, True, 1.5, MAX_EPOCH+1):
            with self.assertRaises(ValueError):work_one(self.case,now=value)
        for value in (0, True, 3601):
            with self.assertRaises(ValueError):enable_schedule(self.case,base_delay_seconds=value)
        with self.assertRaises(ValueError):due_time(MAX_EPOCH,1)
        enable_schedule(self.case)
        with self.assertRaises(ValueError):pause_schedule(self.case,'yes')
        with closing(sqlite3.connect(self.case/'queue.sqlite3')) as db,db:
            db.execute('DROP TABLE scheduler_control')
        with self.assertRaisesRegex(ValueError,'extension_incomplete'):work_one(self.case,now=1000)
        self.assertEqual(jobs(self.case)[0]['attempts'],0)

    def test_running_legacy_job_refuses_implicit_schedule_conversion(self):
        with patch('pipelines.synthetic_ingestion.import_archive',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):
            work_one(self.case)
        with self.assertRaisesRegex(ValueError,'recovery_first'):enable_schedule(self.case)
        self.assertNotIn('not_before',jobs(self.case)[0])

    def test_clock_reversal_waits_and_completion_time_sets_delay(self):
        enable_schedule(self.case)
        with patch('pipelines.synthetic_ingestion.time.time',side_effect=[1000,1005]),patch('pipelines.synthetic_ingestion.import_archive',side_effect=busy()):
            work_one(self.case)
        self.assertEqual(jobs(self.case)[0]['not_before'],1035)
        self.assertIsNone(work_one(self.case,now=900))
        self.assertIsNone(work_one(self.case,now=1034))

    def test_demo_reconciles_policy_and_preserves_previous_case(self):
        original = (self.case/'queue.sqlite3').read_bytes()
        result = verify(self.root/'drill')
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['checks']),13)
        self.assertEqual(result['counts'],dict(flights=4,imports=2,observed_bts=0))
        self.assertTrue(result['busy_fault_injected'])
        self.assertFalse(result['background_scheduler_installed'])
        self.assertEqual((self.case/'queue.sqlite3').read_bytes(),original)
        with self.assertRaises(FileExistsError):verify(self.root/'drill')

    def test_actual_cli_and_no_database_argument(self):
        command = [sys.executable,'-m','pipelines.verify_retry_scheduling']
        result = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])
        rejected = subprocess.run([*command,'--database','PRIVATE_PATH'],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(rejected.returncode,2)


if __name__ == '__main__':unittest.main()
