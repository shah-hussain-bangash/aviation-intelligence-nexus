import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from services.api.monitoring import Monitor
from services.api.main import create_app


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.now = 0

    def tearDown(self):
        self.folder.cleanup()

    def monitor(self, probes=None, enabled=True):
        return Monitor(self.root / 'monitoring.json', probes or {'database': lambda: True},
                       enabled=enabled, clock=lambda: self.now)

    def test_no_sample_disabled_or_stale_never_reports_healthy(self):
        monitor = self.monitor()
        self.assertEqual(monitor.snapshot()['state'], 'unknown')
        monitor.sample()
        self.assertEqual(monitor.snapshot()['state'], 'healthy')
        self.now = 91
        self.assertEqual(monitor.snapshot()['state'], 'unknown')
        self.assertEqual(monitor.snapshot()['components'], {})
        disabled = self.monitor(enabled=False)
        disabled.sample()
        self.assertEqual(disabled.snapshot()['state'], 'disabled')

    def test_failure_and_recovery_transitions_are_not_repeated(self):
        state = [False]
        monitor = self.monitor({'database': lambda: state[0]})
        monitor.sample(); monitor.sample()
        self.assertEqual(monitor.snapshot()['state'], 'degraded')
        self.assertEqual(len(monitor.snapshot()['transitions']), 1)
        state[0] = True
        monitor.sample()
        self.assertEqual(monitor.snapshot()['state'], 'healthy')
        self.assertEqual(monitor.snapshot()['transitions'][0]['state'], 'recovered')

    def test_probe_exception_is_sanitized_and_other_probes_continue(self):
        def bad():
            raise RuntimeError('DO-NOT-RECORD-private-exception')
        monitor = self.monitor({'database': bad, 'active_model': lambda: True})
        monitor.sample()
        snapshot = monitor.snapshot()
        self.assertFalse(snapshot['components']['database'])
        self.assertTrue(snapshot['components']['active_model'])
        self.assertNotIn('DO-NOT-RECORD', (self.root / 'monitoring.json').read_text())

    def test_snapshot_write_failure_is_visible_and_does_not_crash(self):
        monitor = self.monitor()
        with patch.object(Path, 'replace', side_effect=OSError('private filesystem detail')):
            monitor.sample()
        self.assertFalse(monitor.snapshot()['persistence_ok'])
        self.assertEqual(monitor.snapshot()['state'], 'degraded')
        monitor.sample()
        self.assertTrue(monitor.snapshot()['persistence_ok'])

    def test_recordings_are_bounded_and_new_process_does_not_reuse_old_health(self):
        monitor = self.monitor()
        for i in range(300):
            monitor.record(503, i)
        monitor.sample()
        snapshot = monitor.snapshot()
        self.assertEqual(snapshot['request_counts']['5xx'], 300)
        self.assertEqual(len(snapshot['recent_server_failures']), 50)
        self.assertEqual(snapshot['latency']['sample_size'], 200)
        self.assertEqual(snapshot['latency']['p95_ms'], 289)
        record = json.loads((self.root / 'monitoring.json').read_text())
        self.assertEqual(len(record['recent_server_failures']), 50)
        restarted = self.monitor()
        self.assertEqual(restarted.snapshot()['state'], 'unknown')
        self.assertEqual(restarted.snapshot()['request_counts'], {})

    def test_background_task_can_start_and_stop(self):
        async def check():
            monitor = self.monitor()
            monitor.start()
            for _ in range(200):
                if monitor.snapshot()['checked_at']:
                    break
                await asyncio.sleep(.01)
            await monitor.stop()
            self.assertTrue(monitor.task.done())
            self.assertEqual(monitor.snapshot()['state'], 'healthy')
        asyncio.run(check())

    def test_monitoring_access_roles_and_request_data_redaction(self):
        with patch.dict('os.environ', {'AIN_MONITOR_ENABLED': '0'}):
            app = create_app(self.root / 'ain.sqlite3', research_model_directory=self.root / 'missing')
        password = 'isolated-monitor-fixture-123'
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/v1/research/monitoring?secret=DO-NOT-RECORD').status_code, 401)
            for username, role in [('admin', 'admin'), ('reader', 'viewer'), ('researcher', 'researcher')]:
                app.state.auth_store.create_user(username, password, role)
            for username in ['reader', 'researcher', 'admin']:
                login = client.post('/api/v1/auth/login', json={'username': username, 'password': password},
                                    headers={'Origin': 'http://localhost:8080'})
                self.assertEqual(login.status_code, 200)
                result = client.get('/api/v1/research/monitoring')
                self.assertEqual(result.status_code, 200 if username == 'admin' else 403)
            body = result.json()
            self.assertEqual(body['state'], 'disabled')
            self.assertNotIn(password, json.dumps(body))
            self.assertNotIn('DO-NOT-RECORD', json.dumps(body))
            self.assertGreaterEqual(body['request_counts']['4xx'], 3)
            before = app.state.monitor.snapshot()['request_counts']
            client.get('/api/v1/research/monitoring')
            client.get('/health/live')
            self.assertEqual(app.state.monitor.snapshot()['request_counts'], before)

    def test_actual_api_model_failure_is_recorded_without_payload(self):
        with patch.dict('os.environ', {'AIN_MONITOR_ENABLED': '0'}):
            app = create_app(self.root / 'ain.sqlite3', research_model_directory=self.root / 'missing')
        with TestClient(app) as client:
            app.state.auth_store.create_user('admin', 'isolated-monitor-fixture-123', 'admin')
            headers = {'Origin': 'http://localhost:8080'}
            login = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'isolated-monitor-fixture-123'}, headers=headers)
            headers['X-CSRF-Token'] = login.json()['csrf_token']
            result = client.post('/api/v1/research/predict', headers=headers, json={'carrier': 'AA', 'origin': 'JFK', 'destination': 'LAX', 'flight_date': '2025-05-15', 'scheduled_departure': '09:00'})
            self.assertEqual(result.status_code, 503)
            body = client.get('/api/v1/research/monitoring').json()
            self.assertEqual(body['request_counts']['5xx'], 1)
            self.assertEqual(body['recent_server_failures'][0]['status'], 503)
            self.assertNotIn('JFK', json.dumps(body))
