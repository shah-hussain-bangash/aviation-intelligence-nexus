import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pipelines.inspect_runner_status import inspect,timestamp,MAX_BYTES
from pipelines.run_synthetic_ingestion import run
from pipelines.synthetic_ingestion import create_case,enqueue,enable_schedule
from pipelines.verify_import_safety import BASE
from pipelines.verify_runner_recovery import verify
from services.api.paths import ROOT


class RunnerStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.case=create_case(self.root/'case');enqueue(self.case,BASE,year=2025,month=1)
        enable_schedule(self.case);self.record=run(self.case,max_seconds=5)
        self.path=self.case/'runner-status.json';self.checked=timestamp(self.record['checked_at'])

    def tearDown(self):self.temp.cleanup()

    def save(self,value):self.path.write_text(json.dumps(value),encoding='utf-8')

    def test_terminal_snapshot_is_readonly_and_not_current_queue_health(self):
        before=self.path.read_bytes();entries=sorted(p.name for p in self.case.iterdir())
        result=inspect(self.case,now=self.checked+3600)
        self.assertEqual(result['classification'],'recorded_terminal_snapshot')
        self.assertFalse(result['fresh']);self.assertFalse(result['process_liveness_verified'])
        self.assertFalse(result['queue_state_verified']);self.assertFalse(result['status_authenticated'])
        self.assertEqual(result['status_sha256'],hashlib.sha256(before).hexdigest())
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(sorted(p.name for p in self.case.iterdir()),entries)

    def test_running_freshness_boundary_and_future_timestamp(self):
        self.record['state']='running';self.save(self.record)
        self.assertEqual(inspect(self.case,now=self.checked+60)['classification'],'recent_running_snapshot')
        self.assertEqual(inspect(self.case,now=self.checked+60.001)['classification'],'stale_running_snapshot')
        self.assertEqual(inspect(self.case,now=self.checked-1)['classification'],'unavailable')

    def test_invalid_flags_unknown_fields_and_malformed_outcomes_fail_closed(self):
        for change in (lambda d:d.update(production_ready=True),lambda d:d.update(state='healthy'),
                       lambda d:d.update(private_path='PRIVATE'),lambda d:d.update(max_steps=True),
                       lambda d:d.update(elapsed_seconds=float('nan')),
                       lambda d:d['work_results'][0].update(job_id='../PRIVATE'),
                       lambda d:d['work_results'][0].update(attempts=99)):
            value=copy.deepcopy(self.record);change(value);self.save(value)
            result=inspect(self.case)
            self.assertEqual(result['classification'],'unavailable')
            self.assertNotIn('PRIVATE',json.dumps(result))

    def test_missing_oversized_duplicate_key_and_bad_json(self):
        other=create_case(self.root/'missing')
        self.assertEqual(inspect(other)['classification'],'unavailable')
        self.assertFalse((other/'runner-status.json').exists())
        for data in (b'x'*(MAX_BYTES+1),b'{bad',b'{"format":"first","format":"second"}'):
            self.path.write_bytes(data)
            self.assertEqual(inspect(self.case)['classification'],'unavailable')

    def test_bad_inspector_settings_do_not_write(self):
        before=self.path.read_bytes()
        for options in ({'stale_after':0},{'stale_after':True},{'now':float('inf')},{'now':-1}):
            self.assertEqual(inspect(self.case,**options)['classification'],'unavailable')
        self.assertEqual(self.path.read_bytes(),before)

    def test_actual_runner_crash_recovery_and_preserved_orphan_evidence(self):
        result=verify(self.root/'drill')
        self.assertTrue(result['passed']);self.assertEqual(len(result['checks']),12)
        self.assertEqual(result['crash_exit_code'],74)
        self.assertEqual(result['counts'],dict(flights=3,imports=1,observed_bts=0))
        self.assertEqual(result['recovered_run']['work_results'][0]['import_status'],'already_imported')
        self.assertEqual(hashlib.sha256((self.root/'drill/orphaned-runner-status.json').read_bytes()).hexdigest(),result['orphaned_status_sha256'])
        with self.assertRaises(FileExistsError):verify(self.root/'drill')

    def test_actual_inspection_cli_and_redacted_missing_case(self):
        command=[sys.executable,'-m','pipelines.inspect_runner_status']
        result=subprocess.run([*command,str(self.case)],cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['classification'],'recorded_terminal_snapshot')
        bad=subprocess.run([*command,str(self.root/'PRIVATE_MISSING')],cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(bad.returncode,2)
        self.assertNotIn('PRIVATE_MISSING',bad.stdout)


if __name__=='__main__':unittest.main()
