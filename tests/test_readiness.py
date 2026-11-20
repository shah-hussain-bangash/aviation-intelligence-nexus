import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from infra.readiness import assessment, digest
from services.api.main import create_app
from services.api.paths import ROOT


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        catalog = json.loads((ROOT / 'infra/readiness.json').read_text(encoding='utf-8'))
        paths = {'infra/readiness.json', catalog['baseline_path']} | {e['path'] for r in catalog['requirements'] for e in r['evidence']}
        for name in paths:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def tearDown(self):
        self.folder.cleanup()

    def alter(self, action):
        path = self.root / 'infra/readiness.json'
        catalog = json.loads(path.read_text())
        action(catalog)
        path.write_text(json.dumps(catalog))

    def test_complete_scope_is_not_a_production_acceptance_and_handles_windows_line_endings(self):
        result = assessment(self.root)
        self.assertEqual(result['production_open'], 24)
        self.assertEqual(result['production_accepted'], 0)
        self.assertEqual(result['with_local_evidence'], 22)
        self.assertFalse(result['production_ready'])
        path = self.root / 'docs/DEVELOPMENT.md'
        path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        self.assertEqual(assessment(self.root)['evidence_unavailable'], 0)
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_missing_changed_evidence_is_withheld_and_baseline_change_blocks_assessment(self):
        path = self.root / 'docs/LOCAL_IDENTITY.md'
        path.unlink()
        result = assessment(self.root)
        row = next(r for r in result['requirements'] if r['id'] == 'P12')
        self.assertEqual(row['assessment_state'], 'evidence_unavailable')
        self.assertFalse(row['evidence'][0]['integrity_verified'])
        baseline = self.root / 'docs/reports/AIN_Completion_Report.json'
        baseline.write_text('{}')
        with self.assertRaises(ValueError):
            assessment(self.root)

    def test_unsafe_paths_missing_requirements_and_fabricated_acceptance_are_rejected(self):
        self.alter(lambda c: c['requirements'][0]['evidence'][0].update(path='../../private.json'))
        with self.assertRaises(ValueError):
            assessment(self.root)
        shutil.copyfile(ROOT / 'infra/readiness.json', self.root / 'infra/readiness.json')
        self.alter(lambda c: c['requirements'].pop())
        with self.assertRaises(ValueError):
            assessment(self.root)
        shutil.copyfile(ROOT / 'infra/readiness.json', self.root / 'infra/readiness.json')
        self.alter(lambda c: c['requirements'][0].update(production_accepted=True))
        with self.assertRaises(ValueError):
            assessment(self.root)

    def test_api_requires_sign_in_and_returns_503_without_valid_evidence(self):
        app = create_app(self.root / 'private.sqlite3')
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/v1/research/readiness').status_code, 401)
            app.state.auth_store.create_user('admin', 'isolated-readiness-fixture-123', 'admin')
            app.state.auth_store.create_user('reader', 'isolated-readiness-fixture-123', 'viewer')
            client.post('/api/v1/auth/login', headers={'Origin': 'http://localhost:8080'}, json={'username': 'reader', 'password': 'isolated-readiness-fixture-123'})
            with patch('services.api.main.assessment', side_effect=lambda: assessment(self.root)):
                response = client.get('/api/v1/research/readiness')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['total'], 24)
            with patch('services.api.main.assessment', side_effect=ValueError('private implementation details')):
                response = client.get('/api/v1/research/readiness')
                self.assertEqual(response.status_code, 503)
                self.assertNotIn('private implementation details', response.text)
