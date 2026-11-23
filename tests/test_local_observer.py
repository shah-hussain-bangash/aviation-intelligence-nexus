from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from infra.local_observer import exclusive, observe, probe, status


class LocalObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def record(self, **values):
        payload = {'format': 'ain-monitor-v1', 'checked_at': self.now.isoformat(),
                   'production_ready': False, 'components': {'api_readiness': True, 'frontend_liveness': True}}
        payload.update(values)
        (self.root / 'health.json').write_text(json.dumps(payload), encoding='utf-8')

    def test_status_expires_and_future_or_naive_timestamps_never_establish_health(self):
        self.record()
        self.assertEqual(status(self.root, self.now)['state'], 'healthy')
        self.assertEqual(status(self.root, self.now + timedelta(seconds=15))['state'], 'unknown')
        self.assertEqual(status(self.root, self.now + timedelta(seconds=14.999))['state'], 'unknown')
        self.assertEqual(status(self.root, self.now - timedelta(seconds=1))['state'], 'unknown')
        self.record(checked_at='2026-01-01T00:00:00')
        self.assertEqual(status(self.root)['state'], 'unknown')

    def test_degraded_malformed_and_oversized_records(self):
        self.record(components={'api_readiness': False, 'frontend_liveness': True})
        self.assertEqual(status(self.root, self.now)['state'], 'degraded')
        for components in ({}, ['api_readiness', 'frontend_liveness'], {'api_readiness': 'true', 'frontend_liveness': True}):
            self.record(components=components)
            self.assertEqual(status(self.root, self.now)['state'], 'unknown')
        (self.root / 'health.json').write_text('x' * 64001)
        self.assertEqual(status(self.root)['state'], 'unknown')

    def test_probe_requires_bounded_valid_dashboard_json_and_exact_booleans(self):
        with patch('infra.local_observer.build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.status = 200
            for payload, expected in [({'service': 'ain-dashboard', 'backend_ready': True, 'production_ready': False}, True),
                                      ({'service': 'ain-dashboard', 'backend_ready': 'true', 'production_ready': False}, False),
                                      ({'service': 'other'}, False)]:
                response.read.return_value = json.dumps(payload).encode()
                self.assertEqual(probe(8090, True), expected)
            response.read.return_value = b'x' * 4097
            self.assertFalse(probe(8090, False))
            response.read.return_value = b'[]'
            self.assertFalse(probe(8090, False))
        with self.assertRaises(ValueError):probe(8080, True)

    def test_probe_transport_failure_is_unhealthy(self):
        with patch('infra.local_observer.build_opener', side_effect=OSError('private')):
            self.assertFalse(probe(8090, True))

    def test_duplicate_process_is_rejected_and_lock_is_released(self):
        code = 'from infra.local_observer import exclusive;import sys;from pathlib import Path\nwith exclusive(Path(sys.argv[1])):pass'
        with exclusive(self.root):
            process = subprocess.run([sys.executable, '-c', code, str(self.root)], capture_output=True)
            self.assertNotEqual(process.returncode, 0)
        process = subprocess.run([sys.executable, '-c', code, str(self.root)], capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_stop_and_persistence_failure_are_explicit(self):
        with patch('infra.local_observer.private_target', return_value=self.root):
            (self.root / 'stop.request').touch()
            with self.assertRaises(ValueError):observe(self.root, once=True)
            (self.root / 'stop.request').unlink()
            with patch('infra.local_observer.probe', return_value=True), patch('pathlib.Path.replace', side_effect=OSError('private')):
                with self.assertRaises(OSError):observe(self.root, once=True)

    def test_once_writes_only_bounded_monitoring_metadata(self):
        with patch('infra.local_observer.private_target', return_value=self.root), patch('infra.local_observer.probe', return_value=True):
            observe(self.root, once=True)
        self.assertEqual(status(self.root)['state'], 'healthy')
        record = json.loads((self.root / 'health.json').read_text())
        self.assertFalse(record['production_ready'])
        self.assertEqual(record['request_counts'], {})
