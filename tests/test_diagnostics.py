import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from services.api.main import create_app
from services.api.diagnostics import load_diagnostics, summarize, REPORT
from services.api.paths import ROOT


class DiagnosticsTests(unittest.TestCase):
    def test_recorded_populations_and_calibration_error_reconcile(self):
        data=load_diagnostics()
        may=data['periods']['test']['model']
        self.assertEqual((may['records'],may['false_alerts'],may['missed_delays']),(597574,241732,36371))
        self.assertAlmostEqual(may['binned_ece'],0.04094139713990346)
        self.assertAlmostEqual(data['periods']['validation']['model']['binned_ece'],0.012217606880382837)
        self.assertEqual(sum(v['records'] for v in data['carriers'].values()),may['records'])
        self.assertEqual(len(data['carriers']),14)
        self.assertNotIn('dataset_hashes',data)
        self.assertFalse(data['production_ready'])

    def test_report_integrity_missing_and_cross_platform(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(OSError):load_diagnostics(root)
            target=root/REPORT;target.parent.mkdir(parents=True)
            text=(ROOT/REPORT).read_text(encoding='utf-8')
            target.write_bytes(text.replace('\n','\r\n').encode())
            self.assertTrue(load_diagnostics(root)['integrity_verified'])
            target.write_text(text+' ',encoding='utf-8')
            with self.assertRaises(ValueError):load_diagnostics(root)

    def test_inconsistent_counts_rates_and_bins_are_rejected(self):
        original=load_diagnostics()['periods']['test']['model']
        for mutate in [lambda m:m['confusion_matrix_labels_0_1'][0].__setitem__(0,0),
                       lambda m:m.__setitem__('precision',0),
                       lambda m:m['calibration_bins'][0].__setitem__('count',1),
                       lambda m:m['calibration_bins'][0].__setitem__('observed_rate',1),
                       lambda m:m['calibration_bins'][0].__setitem__('bin',True),
                       lambda m:m.__setitem__('roc_auc',float('nan'))]:
            metric=json.loads(json.dumps(original));mutate(metric)
            with self.assertRaises(ValueError):summarize(metric)

    def test_authenticated_viewer_read_only_and_safe_unavailability(self):
        with tempfile.TemporaryDirectory() as folder:
            app=create_app(Path(folder)/'fixture.sqlite3')
            with TestClient(app) as client:
                path='/api/v1/research/model-diagnostics'
                self.assertEqual(client.get(path).status_code,401)
                password='temporary-diagnostic-fixture-123'
                app.state.auth_store.create_user('fixture-admin',password,'admin')
                app.state.auth_store.create_user('fixture-viewer',password,'viewer')
                origin={'Origin':'http://127.0.0.1:8080'}
                login=client.post('/api/v1/auth/login',json={'username':'fixture-viewer','password':password},headers=origin)
                self.assertEqual(login.status_code,200)
                response=client.get(path)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.headers['cache-control'],'no-store')
                client.headers.update({**origin,'X-CSRF-Token':login.json()['csrf_token']})
                self.assertEqual(client.post(path,json={}).status_code,405)
                self.assertEqual(client.get(path+'/arbitrary').status_code,404)
                with patch('services.api.main.load_diagnostics',side_effect=ValueError('private path')):
                    response=client.get(path)
                self.assertEqual(response.status_code,503)
                self.assertNotIn('periods',response.json())
                self.assertNotIn('private path',response.text)
