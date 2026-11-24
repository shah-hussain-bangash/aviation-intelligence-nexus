from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from pipelines import verify_lineage_handoff as handoff
from tests.test_intake_bts import FIELDS,ROW


class LineageHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.archive=self.root/'synthetic.zip';text=io.StringIO();writer=csv.writer(text);writer.writerow(FIELDS);writer.writerow(ROW)
        with zipfile.ZipFile(self.archive,'w') as z:z.writestr('synthetic.csv',text.getvalue())
        self.audit={'months':[{'period':'2025-01','records':1,'manifests':[{'sha256':hashlib.sha256(self.archive.read_bytes()).hexdigest(),'rows_read':1}]}]}
        self.patches=[patch('infra.recovery.ROOT',self.root),patch('services.api.batch_lineage.load_quality',return_value=self.audit),
            patch.dict('os.environ',{k:'0' for k in ('AIN_AGENT_JOBS','AIN_MONITOR_ENABLED','AIN_INTAKE_OVERVIEW_MOUNTED','AIN_CONTAINER')})]
        for p in self.patches:p.start()
        self.directory=self.root/'.local/verification'
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def test_one_command_handoff_uses_real_isolated_api_roles_and_retains_evidence(self):
        report=handoff.verify(self.archive,self.directory)
        self.assertTrue(report['passed']);self.assertEqual(report['dataset']['recorded_rows'],1)
        self.assertEqual(len(report['checks']),11);self.assertTrue(all(report['checks'].values()))
        self.assertEqual(json.loads((self.directory/'result.json').read_text()),report)
        self.assertTrue((self.directory/'state/ain.sqlite3').is_file())
        self.assertTrue((self.directory/'state/intake-dashboard/batch-lineage.json').is_file())
        for flag in ('primary_database_accessed','import_performed','deployment_performed','production_ready'):self.assertFalse(report[flag])
        self.assertNotIn('password',json.dumps(report));self.assertNotIn('session_cookie',json.dumps(report));self.assertNotIn(str(self.root),json.dumps(report))

    def test_existing_case_is_never_reused_or_overwritten(self):
        self.directory.mkdir(parents=True);marker=self.directory/'result.json';marker.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):handoff.verify(self.archive,self.directory)
        self.assertEqual(marker.read_bytes(),b'preserve');self.assertEqual(list(self.directory.iterdir()),[marker])

    def test_quarantined_batch_keeps_failure_stage_and_never_creates_account_database(self):
        self.archive.write_bytes(b'not a zip')
        with self.assertRaises(ValueError):handoff.verify(self.archive,self.directory)
        failure=json.loads((self.directory/'failure.json').read_text())
        self.assertEqual(failure['stage'],'preflight');self.assertFalse(failure['passed'])
        self.assertEqual(len(list((self.directory/'intake/quarantined').iterdir())),1)
        self.assertFalse((self.directory/'state/ain.sqlite3').exists())

    def test_manifest_mismatch_fails_before_api_and_retains_receipt(self):
        self.audit['months'][0]['manifests'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):handoff.verify(self.archive,self.directory)
        self.assertEqual(json.loads((self.directory/'failure.json').read_text())['stage'],'export')
        self.assertEqual(len(list((self.directory/'intake/accepted').glob('*/receipt.json'))),1)
        self.assertFalse((self.directory/'state/ain.sqlite3').exists())

    def test_runtime_workers_or_mounts_are_rejected_before_any_case_write(self):
        for key in ('AIN_AGENT_JOBS','AIN_MONITOR_ENABLED','AIN_INTAKE_OVERVIEW_MOUNTED','AIN_CONTAINER'):
            with patch.dict('os.environ',{key:'1'}):
                with self.assertRaises(ValueError):handoff.verify(self.archive,self.directory)
            self.assertFalse(self.directory.exists())

    def test_cli_failure_does_not_expose_exception_or_personal_paths(self):
        output=io.StringIO()
        with patch('sys.argv',['verify_lineage_handoff',str(self.archive)]),patch.object(handoff,'verify',side_effect=ValueError('PRIVATE-DETAIL')),redirect_stdout(output):
            with self.assertRaises(SystemExit) as error:handoff.main()
        self.assertEqual(error.exception.code,2)
        self.assertEqual(json.loads(output.getvalue()),{'passed':False,'error':'lineage_handoff_failed','production_ready':False})
