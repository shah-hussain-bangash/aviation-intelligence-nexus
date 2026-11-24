from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from pipelines.import_bts import import_archive
from pipelines.synthetic_ingestion import create_case, enqueue, enable_schedule, jobs, pause_schedule
from pipelines.run_synthetic_ingestion import run, request_stop, runner_lock
from pipelines.verify_import_safety import BASE
from pipelines.verify_ingestion_runner import verify
from services.api.paths import ROOT


class IngestionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.case=create_case(self.root/'case')
        enqueue(self.case,BASE,year=2025,month=1); enable_schedule(self.case)

    def tearDown(self):self.temp.cleanup()

    def test_foreground_run_drains_and_records_status(self):
        result=run(self.case,max_seconds=5)
        self.assertEqual(result['state'],'drained')
        self.assertEqual(len(result['work_results']),1)
        self.assertEqual(jobs(self.case)[0]['state'],'succeeded')
        self.assertEqual(json.loads((self.case/'runner-status.json').read_text(encoding='utf-8')),result)
        self.assertFalse(result['background_service_installed'])

    def test_stop_and_pause_do_not_consume_attempts(self):
        pause_schedule(self.case,True)
        self.assertEqual(run(self.case)['state'],'paused')
        self.assertEqual(jobs(self.case)[0]['attempts'],0)
        pause_schedule(self.case,False); request_stop(self.case)
        self.assertEqual(run(self.case)['state'],'stopped')
        self.assertEqual(jobs(self.case)[0]['attempts'],0)
        self.assertTrue((self.case/'stop.request').exists())

    def test_stop_during_import_finishes_current_batch_and_leaves_next_queued(self):
        february=[*BASE[0]]; february[0]='2025-02-01'
        enqueue(self.case,[february],year=2025,month=2)
        def stopped(*args,**kwargs):
            result=import_archive(*args,**kwargs); request_stop(self.case); return result
        with patch('pipelines.synthetic_ingestion.import_archive',side_effect=stopped):
            result=run(self.case,max_seconds=5)
        self.assertEqual(result['state'],'stopped')
        self.assertEqual([r['state'] for r in jobs(self.case)],['succeeded','queued'])

    def test_duration_limit_waits_without_claiming_future_job(self):
        with closing(sqlite3.connect(self.case/'queue.sqlite3')) as db,db:
            db.execute('UPDATE jobs SET not_before=?',(int(time.time())+3600,))
        result=run(self.case,max_seconds=1,poll_seconds=0.05)
        self.assertEqual(result['state'],'duration_limit')
        self.assertGreater(result['wait_cycles'],0)
        self.assertEqual(jobs(self.case)[0]['attempts'],0)

    def test_step_limit_and_next_invocation_preserve_work(self):
        february=[*BASE[0]]; february[0]='2025-02-01'
        enqueue(self.case,[february],year=2025,month=2)
        self.assertEqual(run(self.case,max_steps=1)['state'],'step_limit')
        result=run(self.case,max_steps=5)
        self.assertEqual(result['state'],'drained')
        self.assertEqual(len(result['work_results']),1)
        self.assertEqual([row['attempts'] for row in jobs(self.case)],[1,1])

    def test_second_process_cannot_own_runner_lock(self):
        code='''import sys
from pipelines.run_synthetic_ingestion import run
try:run(sys.argv[1])
except ValueError as error:raise SystemExit(0 if str(error)=='synthetic_runner_busy' else 4)
raise SystemExit(5)
'''
        with runner_lock(self.case):
            result=subprocess.run([sys.executable,'-c',code,str(self.case)],cwd=ROOT,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(jobs(self.case)[0]['attempts'],0)

    def test_quarantine_is_review_required_not_healthy_drain(self):
        job=jobs(self.case)[0]
        (self.case/'archives'/(job['job_id']+'.zip')).write_bytes(b'bad')
        self.assertEqual(run(self.case)['state'],'needs_review')
        self.assertEqual(jobs(self.case)[0]['state'],'quarantined')

    def test_failure_and_interrupt_record_fixed_status(self):
        with patch('pipelines.run_synthetic_ingestion.work_one',side_effect=ValueError('PRIVATE DETAIL')):
            result=run(self.case)
        self.assertEqual(result['state'],'failed')
        self.assertNotIn('PRIVATE DETAIL',json.dumps(result))
        with patch('pipelines.run_synthetic_ingestion.work_one',side_effect=KeyboardInterrupt):
            self.assertEqual(run(self.case)['state'],'interrupted')
        self.assertEqual(jobs(self.case)[0]['attempts'],0)

    def test_admission_and_actual_runner_cli(self):
        for options in ({'max_seconds':0},{'max_seconds':True},{'max_steps':101},{'poll_seconds':float('nan')},{'poll_seconds':0.001}):
            with self.assertRaises(ValueError):run(self.case,**options)
        legacy=create_case(self.root/'legacy'); enqueue(legacy,BASE,year=2025,month=1)
        with self.assertRaisesRegex(ValueError,'scheduler_not_enabled'):run(legacy)
        self.assertFalse((legacy/'runner-status.json').exists())
        result=subprocess.run([sys.executable,'-m','pipelines.run_synthetic_ingestion',str(self.case),'--max-seconds','5'],cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['state'],'drained')

    def test_integrated_demo_is_synthetic_and_never_overwrites(self):
        result=verify(self.root/'drill')
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['checks']),12)
        self.assertTrue(result['busy_fault_injected'])
        self.assertFalse(result['primary_database_accessed'])
        self.assertNotIn(str(self.root),json.dumps(result))
        with self.assertRaises(FileExistsError):verify(self.root/'drill')


if __name__=='__main__':unittest.main()
