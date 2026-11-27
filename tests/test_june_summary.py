import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from services.api.main import create_app
from services.api.paths import ROOT
from services.api.june_evaluation import load_june_evaluation, REPORT, REPORT_SHA256, MAX_BYTES


class JuneSummaryTests(unittest.TestCase):
    def test_pinned_result_counts_metrics_and_limits(self):
        result = load_june_evaluation()
        self.assertEqual(result['report_sha256'], REPORT_SHA256)
        self.assertTrue(result['integrity_verified'])
        self.assertEqual(result['data_counts']['rows_read'], 611575)
        self.assertEqual(result['model']['records'], 599472)
        self.assertAlmostEqual(result['model']['roc_auc'], .6705555947934609)
        self.assertEqual(result['frozen_threshold'], .17)
        self.assertEqual(result['uncertainty']['date_clusters'], 30)
        self.assertEqual(result['cohort_inventory'], {'carrier': 14, 'origin': 345})
        for flag in ('inference_executed_by_request', 'globally_untouched_holdout_established',
                     'source_rights_verified', 'operational_approval', 'production_ready'):
            self.assertIs(result[flag], False)
        self.assertNotIn('private_report_sha256', result)
        self.assertNotIn('attempt_receipt_sha256', result)
        self.assertNotIn('.local', json.dumps(result))
        self.assertLess(len(json.dumps(result)), 10000)

    def test_missing_changed_oversized_and_windows_line_endings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(OSError):
                load_june_evaluation(root)
            target = root / REPORT
            target.parent.mkdir(parents=True)
            text = (ROOT / REPORT).read_text(encoding='utf-8')
            target.write_bytes(text.replace('\n', '\r\n').encode())
            self.assertTrue(load_june_evaluation(root)['integrity_verified'])
            for raw in ((text + ' ').encode(), b'x' * (MAX_BYTES + 1), b'\xff'):
                target.write_bytes(raw)
                with self.assertRaises(ValueError):
                    load_june_evaluation(root)

    def test_all_signed_in_roles_read_only_without_overrides(self):
        path = '/api/v1/research/june-evaluation'
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Path(folder) / 'test.sqlite3')
            with TestClient(app) as client:
                self.assertEqual(client.get(path).status_code, 401)
                password = 'synthetic-june-summary-password'
                origin = {'Origin': 'http://127.0.0.1:8080'}
                for role in ('admin', 'researcher', 'viewer'):
                    app.state.auth_store.create_user('june-' + role, password, role)
                    login = client.post('/api/v1/auth/login', headers=origin,
                        json={'username': 'june-' + role, 'password': password})
                    self.assertEqual(login.status_code, 200)
                    client.headers.update({**origin, 'X-CSRF-Token': login.json()['csrf_token']})
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers['cache-control'], 'no-store')
                    self.assertEqual(response.json(), load_june_evaluation())
                    for query in ('?month=2025-07', '?path=.local/model', '?threshold=0.5'):
                        self.assertEqual(client.get(path + query).status_code, 422)
                    for method in ('post', 'put', 'patch', 'delete'):
                        self.assertEqual(getattr(client, method)(path).status_code, 405)
                    self.assertEqual(client.get(path + '/other').status_code, 404)
                    self.assertEqual(client.post('/api/v1/auth/logout').status_code, 200)
                    self.assertEqual(client.get(path).status_code, 401)

    def test_missing_or_changed_report_withholds_all_results_and_error_details(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Path(folder) / 'test.sqlite3')
            with TestClient(app) as client:
                password = 'synthetic-june-summary-password'
                app.state.auth_store.create_user('june-admin', password, 'admin')
                client.post('/api/v1/auth/login', headers={'Origin': 'http://127.0.0.1:8080'},
                    json={'username': 'june-admin', 'password': password})
                for error in (OSError('private filename'), ValueError('private filename')):
                    with patch('services.api.main.load_june_evaluation', side_effect=error):
                        response = client.get('/api/v1/research/june-evaluation')
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.headers['cache-control'], 'no-store')
                    self.assertNotIn('private filename', response.text)
                    self.assertNotIn('model', response.json())
