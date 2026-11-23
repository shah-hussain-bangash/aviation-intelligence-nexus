import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from fastapi.testclient import TestClient
from pipelines.intake_bts import intake
from pipelines.intake_overview import collect, export
from services.api.intake_overview import validate, load_overview
from services.api.main import create_app
from tests.test_intake_bts import FIELDS, ROW


class IntakeOverviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.directory=self.root/'.local/intake'
        self.source=self.root/'source.zip'; text=io.StringIO(); writer=csv.writer(text); writer.writerow(FIELDS); writer.writerow(ROW)
        with zipfile.ZipFile(self.source,'w') as z: z.writestr('data.csv',text.getvalue())
        for _ in range(2): intake(self.source,self.directory,2025,1)

    def tearDown(self): self.temp.cleanup()

    def test_unique_hash_dedup_and_quarantine_and_unverifiable_accounting_readonly(self):
        bad=self.root/'bad.zip'; bad.write_bytes(b'invalid'); intake(bad,self.directory,2025,1)
        (self.directory/'accepted'/'broken').mkdir()
        before={str(p):p.read_bytes() for p in self.directory.rglob('*') if p.is_file()}
        r=collect(self.directory)
        self.assertEqual((r['runs_checked'],r['accepted_runs'],r['quarantined_runs'],r['unverifiable_runs']),(4,2,1,1))
        self.assertEqual((r['unique_archives'],r['declared_rows'],r['repeated_accepted_runs']),(1,1,1))
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.directory.rglob('*') if p.is_file()})
        self.assertNotIn(str(self.root),json.dumps(r)); self.assertFalse(r['import_authorized'])

    def test_conflicting_unsigned_claims_fail_whole_export_and_preserve_previous(self):
        first=export(self.root); target=self.root/'.local/intake-dashboard/snapshot.json'; before=target.read_bytes()
        receipt=next((self.directory/'accepted').glob('*/receipt.json')); r=json.loads(receipt.read_text()); r.update(rows_read=2,unique_identities=2); receipt.write_text(json.dumps(r))
        with self.assertRaises(ValueError): export(self.root)
        self.assertEqual(target.read_bytes(),before)
        self.assertEqual(load_overview(self.root/'.local'),first)

    def test_export_is_metadata_only_hashed_and_preserves_previous(self):
        payload=export(self.root); self.assertEqual(load_overview(self.root/'.local'),payload)
        export(self.root); self.assertEqual(len(list((self.root/'.local/intake-dashboard').glob('previous-*.json'))),1)
        target=self.root/'.local/intake-dashboard/snapshot.json'; r=json.loads(target.read_text()); r['payload']['declared_rows']=999; target.write_text(json.dumps(r))
        with self.assertRaises(ValueError): load_overview(self.root/'.local')

    def test_contract_rejects_approval_duplicates_counts_and_private_fields(self):
        original=collect(self.directory)
        for mutate in (lambda r:r.update(production_ready=True),lambda r:r.update(private_path='secret'),lambda r:r.update(accepted_runs=True),lambda r:r.update(declared_rows=2),lambda r:r['archives'].append(copy.deepcopy(r['archives'][0])),lambda r:r.update(quarantine_reasons={'bad':1})):
            value=copy.deepcopy(original); mutate(value)
            with self.assertRaises(ValueError): validate(value)

    def test_budget_and_run_limit_fail_without_partial_snapshot(self):
        times=iter([0,121])
        with self.assertRaises(ValueError): collect(self.directory,clock=lambda:next(times))
        with patch.object(Path,'iterdir',return_value=iter([self.directory/'accepted'/'x']*1001)):
            with self.assertRaises(ValueError): collect(self.directory)

    def test_admin_only_no_query_unavailable_and_no_write_route(self):
        export(self.root); app=create_app(self.root/'.local/ain.sqlite3'); path='/api/v1/research/intake-overview'
        with TestClient(app) as client:
            self.assertEqual(client.get(path).status_code,401)
            password='temporary-intake-fixture-123'; origin={'Origin':'http://127.0.0.1:8080'}
            for role in ('admin','viewer'): app.state.auth_store.create_user('fixture-'+role,password,role)
            for role in ('viewer','admin'):
                self.assertEqual(client.post('/api/v1/auth/login',json={'username':'fixture-'+role,'password':password},headers=origin).status_code,200)
                self.assertEqual(client.get(path).status_code,403 if role=='viewer' else 200)
            self.assertEqual(client.get(path+'?file=secret').status_code,422)
            self.assertNotEqual(client.post(path,json={},headers=origin).status_code,200)
            (self.root/'.local/intake-dashboard/snapshot.json').write_text('{}')
            response=client.get(path); self.assertEqual(response.status_code,503); self.assertNotIn(str(self.root),response.text)

    def test_container_flag_uses_only_fixed_metadata_location(self):
        export(self.root)
        with patch.dict('os.environ',{'AIN_INTAKE_OVERVIEW_MOUNTED':'1'}):
            with self.assertRaises((ValueError,OSError)): load_overview(self.root/'.local')
