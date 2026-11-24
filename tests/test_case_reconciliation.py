from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pipelines.synthetic_ingestion import create_case,enqueue,work_one,enable_schedule,jobs
from pipelines.reconcile_synthetic_case import reconcile
from pipelines.verify_import_safety import BASE
from pipelines.verify_case_reconciliation import verify,fingerprints
from services.api.paths import ROOT


class CaseReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.case=create_case(self.root/'case')
        enqueue(self.case,BASE,year=2025,month=1);work_one(self.case)

    def tearDown(self):self.temp.cleanup()

    def test_reconstructs_selected_rows_and_preserves_source_bytes_and_entries(self):
        before=fingerprints(self.case)
        result=reconcile(self.case,offline_copy=True)
        self.assertTrue(result['consistent'],result)
        self.assertEqual((result['flight_records'],result['import_ledgers']),(3,1))
        self.assertEqual(fingerprints(self.case),before)
        self.assertFalse(result['source_authenticated']);self.assertFalse(result['current_health_verified'])

    def test_changed_rows_and_missing_rows_are_rejected_without_repair(self):
        with closing(sqlite3.connect(self.case/'flights.sqlite3')) as db,db:
            db.execute('UPDATE flights SET arrival_delay_minutes=90 WHERE cancelled=0 AND diverted=0')
        before=fingerprints(self.case);result=reconcile(self.case,offline_copy=True)
        self.assertEqual(result['errors'],['stored_rows_do_not_match_archives'])
        self.assertEqual(fingerprints(self.case),before)

    def test_altered_archive_or_queue_accounting_is_rejected(self):
        record=jobs(self.case)[0]
        with closing(sqlite3.connect(self.case/'queue.sqlite3')) as db,db:
            value=json.loads(record['result_json']);value['rows_inserted']=99
            db.execute('UPDATE jobs SET result_json=?',(json.dumps(value),))
        self.assertEqual(reconcile(self.case,offline_copy=True)['errors'],['queue_result_accounting_mismatch'])
        (self.case/'archives'/(record['job_id']+'.zip')).write_bytes(b'changed')
        self.assertEqual(reconcile(self.case,offline_copy=True)['errors'],['archive_identity_mismatch'])

    def test_offline_ack_sidecar_size_and_pending_guards(self):
        missing=self.root/'PRIVATE_MISSING'
        self.assertEqual(reconcile(missing)['errors'],['explicit_offline_copy_required'])
        self.assertFalse(missing.exists())
        sidecar=self.case/'flights.sqlite3-wal';sidecar.write_bytes(b'not a live database')
        self.assertEqual(reconcile(self.case,offline_copy=True)['errors'],['sqlite_sidecar_present'])
        # Only remove the deliberately created single test file, never source data.
        sidecar.unlink()
        with patch('pipelines.reconcile_synthetic_case.MAX_BYTES',1):
            self.assertEqual(reconcile(self.case,offline_copy=True)['errors'],['file_size_limit'])
        enqueue(self.case,BASE,year=2025,month=1)
        self.assertEqual(reconcile(self.case,offline_copy=True)['errors'],['unfinished_jobs_require_review'])

    def test_overlapping_batches_reconcile_when_execution_order_differs(self):
        other=create_case(self.root/'reordered')
        enqueue(other,[BASE[0]],year=2025,month=1)
        enqueue(other,[BASE[0],BASE[2]],year=2025,month=1)
        enable_schedule(other)
        with closing(sqlite3.connect(other/'queue.sqlite3')) as db,db:
            db.execute('UPDATE jobs SET not_before=1030 WHERE sequence=1')
        work_one(other,now=1000);work_one(other,now=1030)
        result=reconcile(other,offline_copy=True)
        self.assertTrue(result['consistent'],result)
        self.assertEqual((result['flight_records'],result['import_ledgers']),(2,2))

    def test_unacknowledged_committed_ledger_is_not_declared_consistent(self):
        with closing(sqlite3.connect(self.case/'queue.sqlite3')) as db,db:
            db.execute("UPDATE jobs SET state='quarantined',reason='attempt_limit'")
        self.assertFalse(reconcile(self.case,offline_copy=True)['consistent'])
        self.assertEqual(jobs(self.case)[0]['state'],'quarantined')

    def test_demo_positive_negative_and_input_fingerprints(self):
        result=verify(self.root/'drill')
        self.assertTrue(result['passed'],result)
        self.assertEqual(len(result['checks']),10)
        self.assertEqual(result['reconciliation']['flight_records'],4)
        self.assertFalse(result['changed_rows_check']['consistent'])
        self.assertFalse(result['primary_database_accessed'])
        self.assertEqual(result['original_case_sha256'],fingerprints(self.root/'drill/original'))
        with self.assertRaises(FileExistsError):verify(self.root/'drill')

    def test_actual_cli_acknowledgment_and_redacted_missing_input(self):
        command=[sys.executable,'-m','pipelines.reconcile_synthetic_case',str(self.case)]
        missing_ack=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(missing_ack.returncode,2)
        self.assertEqual(json.loads(missing_ack.stdout)['errors'],['explicit_offline_copy_required'])
        result=subprocess.run([*command,'--offline-copy'],cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['consistent'])


if __name__=='__main__':unittest.main()
