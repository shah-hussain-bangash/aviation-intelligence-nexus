import copy
import hashlib
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from tests import test_verify_intake
from services.api.batch_lineage import project,load_lineage
from services.api.data_quality import REPORT_SHA256
from services.api.main import create_app
from pipelines import batch_lineage


class BatchLineageTests(unittest.TestCase):
    def setUp(self):
        test_verify_intake.VerifyIntakeTests.setUp(self)
        text=self.receipt.read_bytes().decode('utf-8');r=json.loads(text)
        self.envelope={'format':'ain-batch-lineage-v1','receipt_text':text,'receipt_sha256':hashlib.sha256(text.encode()).hexdigest(),'dataset_report_sha256':REPORT_SHA256}
        self.audit={'months':[{'period':'2025-01','records':1,'manifests':[{'sha256':r['archive_sha256'],'rows_read':1}]}]}
        self.patch=patch('services.api.batch_lineage.load_quality',return_value=self.audit);self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()

    def test_role_projection_exact_archive_link_and_literal_receipt_digest(self):
        admin=project(self.envelope,'admin');analyst=project(self.envelope,'researcher');viewer=project(self.envelope,'viewer')
        self.assertIn('admin_receipt',admin);self.assertNotIn('admin_receipt',analyst);self.assertEqual(analyst,viewer)
        self.assertEqual(admin['intake']['run_id'],admin['admin_receipt']['run_id'])
        self.assertEqual(analyst['dataset']['archive_sha256'],admin['admin_receipt']['archive_sha256'])
        self.assertFalse(analyst['original_import_receipt']);self.assertNotIn(str(self.root),json.dumps(analyst))

    def test_changed_receipt_wrong_archive_count_or_report_rejected(self):
        for change in (lambda r:r.update(receipt_text=r['receipt_text']+' '),lambda r:r.update(dataset_report_sha256='0'*64),lambda r:r.update(extra='private')):
            value=copy.deepcopy(self.envelope);change(value)
            with self.assertRaises(ValueError):project(value,'admin')
        self.audit['months'][0]['manifests'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):project(self.envelope,'admin')
        self.audit['months'][0]['manifests'][0]['sha256']=json.loads(self.envelope['receipt_text'])['archive_sha256'];self.audit['months'][0]['manifests'][0]['rows_read']=2
        with self.assertRaises(ValueError):project(self.envelope,'viewer')

    def test_api_roles_no_query_and_missing_metadata(self):
        folder=self.root/'intake-dashboard';folder.mkdir();target=folder/'batch-lineage.json';target.write_text(json.dumps(self.envelope),encoding='utf-8')
        app=create_app(self.root/'ain.sqlite3');route='/api/v1/research/batch-lineage'
        with TestClient(app) as client:
            self.assertEqual(client.get(route).status_code,401)
            password='synthetic-lineage-fixture-123';headers={'Origin':'http://127.0.0.1:8080'}
            for role in ('admin','researcher','viewer'):
                app.state.auth_store.create_user('fixture-'+role,password,role)
                self.assertEqual(client.post('/api/v1/auth/login',json={'username':'fixture-'+role,'password':password},headers=headers).status_code,200)
                result=client.get(route);self.assertEqual(result.status_code,200);self.assertEqual('admin_receipt' in result.json(),role=='admin')
                self.assertEqual(client.get(route+'?path=secret').status_code,422)
            target.write_text('{}',encoding='utf-8');self.assertEqual(client.get(route).status_code,503)
            self.assertNotEqual(client.post(route,json={},headers=headers).status_code,200)

    def test_fixed_mount_does_not_fall_back_to_native_metadata(self):
        folder=self.root/'intake-dashboard';folder.mkdir();(folder/'batch-lineage.json').write_text(json.dumps(self.envelope),encoding='utf-8')
        self.assertEqual(load_lineage(self.root,'viewer')['dataset']['recorded_rows'],1)
        with patch.dict('os.environ',{'AIN_INTAKE_OVERVIEW_MOUNTED':'1'}):
            with self.assertRaises((ValueError,OSError)):load_lineage(self.root,'admin')

    def export_paths(self):
        run=self.root/'.local/intake/accepted'/self.run.name
        shutil.copytree(self.run,run)
        return run,self.root/'.local/research-state'

    def test_export_reopens_exact_receipt_without_changing_input_artifacts(self):
        run,state=self.export_paths();before={p.name:p.read_bytes() for p in run.iterdir()}
        with patch('infra.recovery.ROOT',self.root): result=batch_lineage.export(run,state)
        self.assertEqual(before,{p.name:p.read_bytes() for p in run.iterdir()})
        self.assertEqual(result,load_lineage(state,'admin'))
        self.assertEqual(result['intake']['receipt_sha256'],hashlib.sha256(before['receipt.json']).hexdigest())
        self.assertFalse(result['import_performed'])

    def test_export_never_replaces_existing_lineage_record(self):
        run,state=self.export_paths()
        with patch('infra.recovery.ROOT',self.root):
            batch_lineage.export(run,state);target=state/'intake-dashboard/batch-lineage.json';before=target.read_bytes()
            with self.assertRaises(FileExistsError):batch_lineage.export(run,state)
        self.assertEqual(target.read_bytes(),before)

    def test_export_detects_any_receipt_byte_change_during_archive_verification(self):
        run,state=self.export_paths();original=batch_lineage.verify_run
        def changed(directory):
            result=original(directory)
            with (directory/'receipt.json').open('ab') as stream:stream.write(b' ')
            return result
        with patch('infra.recovery.ROOT',self.root),patch('pipelines.batch_lineage.verify_run',side_effect=changed):
            with self.assertRaises(ValueError):batch_lineage.export(run,state)
        self.assertFalse(state.exists())

    def test_export_rejects_oversized_receipt_before_archive_work(self):
        run,state=self.export_paths();(run/'receipt.json').write_bytes(b' '*64001)
        with patch('infra.recovery.ROOT',self.root),patch('pipelines.batch_lineage.verify_run') as verifier:
            with self.assertRaises(ValueError):batch_lineage.export(run,state)
            verifier.assert_not_called()
        self.assertFalse(state.exists())

    def test_export_does_not_publish_a_changed_archive(self):
        run,state=self.export_paths();archive=run/'archive.zip';raw=bytearray(archive.read_bytes());raw[-1]^=1;archive.write_bytes(raw)
        with patch('infra.recovery.ROOT',self.root):
            with self.assertRaises(ValueError):batch_lineage.export(run,state)
        self.assertFalse(state.exists())

    def test_export_cannot_write_outside_private_research_root(self):
        run,state=self.export_paths();outside=self.root/'outside-private-state'
        with patch('infra.recovery.ROOT',self.root):
            with self.assertRaises(ValueError):batch_lineage.export(run,outside)
        self.assertFalse(outside.exists())
