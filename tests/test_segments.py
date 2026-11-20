import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from services.api.main import create_app
from services.api.paths import ROOT
from services.api.segments import load_segments, REPORT


class SegmentViewTests(unittest.TestCase):
    def test_fixed_summary_reconciles_and_excludes_private_artifacts(self):
        data = load_segments()
        self.assertEqual(data['changed_routes'], 875)
        self.assertEqual(sum(map(sum, data['transition_counts'])), data['overlapping_routes'])
        self.assertEqual(data['coverage']['train']['routes_supported'], 2488)
        self.assertTrue(data['integrity_verified'])
        self.assertFalse(data['production_ready'])
        self.assertNotIn('artifact_sha256', data)
        self.assertNotIn('source_imports', data)
        self.assertNotIn('.local', json.dumps(data))

    def test_missing_tampered_and_cross_platform_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(OSError):
                load_segments(root)
            target = root / REPORT
            target.parent.mkdir(parents=True)
            text = (ROOT / REPORT).read_text(encoding='utf-8')
            target.write_bytes(text.replace('\n', '\r\n').encode())
            self.assertTrue(load_segments(root)['integrity_verified'])
            target.write_text(text + ' ', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_segments(root)

    def test_anonymous_denied_viewer_read_allowed_and_writes_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Path(folder) / 'test.sqlite3')
            with TestClient(app) as client:
                path = '/api/v1/research/route-segments'
                self.assertEqual(client.get(path).status_code, 401)
                password = 'temporary-viewer-fixture-123'
                app.state.auth_store.create_user('fixture-admin', password, 'admin')
                app.state.auth_store.create_user('fixture-viewer', password, 'viewer')
                origin = {'Origin': 'http://127.0.0.1:8080'}
                login = client.post('/api/v1/auth/login', json={'username': 'fixture-viewer', 'password': password}, headers=origin)
                self.assertEqual(login.status_code, 200)
                client.headers.update({**origin, 'X-CSRF-Token': login.json()['csrf_token']})
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertEqual(client.post(path, json={}).status_code, 405)
                self.assertEqual(client.get(path + '/arbitrary').status_code, 404)

    def test_unavailable_evidence_returns_no_groups(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Path(folder) / 'test.sqlite3')
            with TestClient(app) as client:
                app.state.auth_store.create_user('fixture-admin', 'temporary-test-fixture-123', 'admin')
                client.post('/api/v1/auth/login', json={'username': 'fixture-admin', 'password': 'temporary-test-fixture-123'}, headers={'Origin': 'http://127.0.0.1:8080'})
                with patch('services.api.main.load_segments', side_effect=ValueError('private path')):
                    response = client.get('/api/v1/research/route-segments')
                self.assertEqual(response.status_code, 503)
                self.assertNotIn('profiles', response.json())
                self.assertNotIn('private path', response.text)
