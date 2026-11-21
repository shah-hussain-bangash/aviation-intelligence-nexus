import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from services.api.monitoring import Monitor,age_between
from infra.monitoring_check import exercise


class MonitoringIntegrityTests(unittest.TestCase):
    def setUp(self):self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);self.clock=0.0
    def tearDown(self):self.folder.cleanup()
    def monitor(self,probes=None):return Monitor(self.root/'monitoring.json',{'database':lambda:True} if probes is None else probes,enabled=True,clock=lambda:self.clock)

    def test_empty_probe_configuration_never_establishes_health(self):
        m=self.monitor({});m.sample();self.assertEqual(m.snapshot()['state'],'unknown');self.assertEqual(m.snapshot()['components'],{})

    def test_exact_boundary_and_rounding_are_conservative(self):
        m=self.monitor();m.sample();self.clock=89.94;self.assertEqual(m.snapshot()['state'],'healthy');self.clock=89.99;self.assertEqual(m.snapshot()['state'],'unknown');self.clock=90;self.assertEqual(m.snapshot()['components'],{})

    def test_backwards_and_invalid_clock_clear_health_without_nan_json(self):
        m=self.monitor();m.sample()
        for value in [-1,float('nan'),float('inf'),None,'invalid',10**1000]:
            self.clock=value;s=m.snapshot();self.assertEqual(s['state'],'unknown');self.assertEqual(s['components'],{});self.assertIsNone(s['sample_age_seconds']);json.dumps(s,allow_nan=False)
        self.assertIsNone(age_between(0,1));self.assertIsNone(age_between(0,'invalid'))

    def test_invalid_measurements_preserve_response_counts_and_never_become_zero(self):
        m=self.monitor()
        for value in [-1,float('nan'),float('inf'),None,'12',True,10**1000]:m.record(200,value)
        s=m.snapshot();self.assertEqual(s['request_counts']['2xx'],7);self.assertEqual(s['latency']['invalid_samples'],7);self.assertEqual(s['latency']['sample_size'],0);self.assertIsNone(s['latency']['p95_ms']);json.dumps(s,allow_nan=False)
        m.record(503,12.5);s=m.snapshot();self.assertEqual(s['latency']['sample_size'],1);self.assertEqual(s['latency']['p95_ms'],12.5);self.assertEqual(s['recent_server_failures'][0]['status'],503)

    def test_non_http_status_is_other_and_cannot_become_server_failure(self):
        m=self.monitor()
        for value in [None,'503',True,99,600]:m.record(value,10)
        s=m.snapshot();self.assertEqual(s['request_counts'],{'other':5});self.assertEqual(s['recent_server_failures'],[])

    def test_window_bounds_and_restart_do_not_hide_invalid_measurements(self):
        m=self.monitor()
        for i in range(300):m.record(200,i)
        m.record(200,-1);m.sample();s=m.snapshot();self.assertEqual(s['latency']['sample_size'],200);self.assertEqual(s['latency']['invalid_samples'],1)
        self.assertEqual(s['latency']['p95_ms'],289);restarted=self.monitor();self.assertEqual(restarted.snapshot()['state'],'unknown');self.assertEqual(restarted.snapshot()['latency']['invalid_samples'],0)

    def test_authenticated_failure_recovery_exercise_is_disposable(self):
        with patch('infra.monitoring_check.ROOT',self.root):result=exercise(self.root/'.local/http-check')
        self.assertTrue(result['passed']);self.assertEqual(len(result['checks']),13);self.assertFalse(result['production_ready'])
