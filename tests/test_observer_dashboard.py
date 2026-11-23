from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from infra.local_observer import deployment_status
from services.api.main import create_app


class ObserverDashboardTests(unittest.TestCase):
    def test_container_requires_explicit_fixed_mount(self):
        with patch.dict(os.environ, {'AIN_CONTAINER': '1', 'AIN_OBSERVER_MOUNTED': '0'}), patch('infra.local_observer.status') as read:
            result = deployment_status(Path('unused'))
        read.assert_not_called()
        self.assertEqual(result['state'], 'unknown')
        self.assertFalse(result['task_runtime_verified'])

    def test_mounted_container_reads_only_fixed_directory(self):
        observation = {'state': 'unknown', 'components': {}, 'production_ready': False, 'external_alert_delivery': False}
        with patch.dict(os.environ, {'AIN_CONTAINER': '1', 'AIN_OBSERVER_MOUNTED': '1'}), patch('infra.local_observer.status', return_value=observation) as read:
            result = deployment_status(Path('not-the-mount'))
        read.assert_called_once_with(Path('/observer'))
        self.assertEqual(result['source_mode'], 'container_readonly_mount')
        self.assertNotIn('/observer', json.dumps(result))

    def test_authenticated_platform_status_is_sanitized_and_observer_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'observer'; folder.mkdir()
            record = folder / 'health.json'
            record.write_text(json.dumps({'format': 'ain-monitor-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
                'components': {'api_readiness': True, 'frontend_liveness': True}, 'production_ready': False,
                'private_field': 'DO-NOT-EXPOSE'}), encoding='utf-8')
            before = record.read_bytes()
            with patch.dict(os.environ, {'AIN_CONTAINER': '0', 'AIN_MONITOR_ENABLED': '0', 'AIN_AGENT_JOBS': '0'}), patch('services.api.main.ollama.models', return_value=[]):
                app = create_app(root / 'fixture.sqlite3', research_model_directory=root / 'missing-model')
                with TestClient(app) as client:
                    endpoint = '/api/v1/research/platform-status'
                    self.assertEqual(client.get(endpoint).status_code, 401)
                    app.state.auth_store.create_user('observer-admin', 'fixture-password-12345', 'admin')
                    app.state.auth_store.create_user('observer-viewer', 'fixture-password-12345', 'viewer')
                    signed = client.post('/api/v1/auth/login', json={'username': 'observer-viewer', 'password': 'fixture-password-12345'}, headers={'Origin': 'http://127.0.0.1:8080'})
                    self.assertEqual(signed.status_code, 200)
                    response = client.get(endpoint)
                    self.assertEqual(response.status_code, 200)
                    observer = response.json()['independent_observer']
                    self.assertEqual(observer['state'], 'healthy')
                    self.assertFalse(observer['task_runtime_verified'])
                    self.assertNotIn('DO-NOT-EXPOSE', response.text)
                    self.assertNotIn(str(root), response.text)
            self.assertEqual(record.read_bytes(), before)
