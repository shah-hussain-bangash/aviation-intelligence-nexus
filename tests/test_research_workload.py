import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import joblib
import pandas as pd
from threadpoolctl import threadpool_limits
from infra.research_workload import bounds, run
from ml.train_v2 import build_model, PROTOCOL_PATH


class ResearchWorkloadTests(unittest.TestCase):
    def test_limits_prevent_unbounded_work(self):
        for requests, workers in [(0, 1), (31, 1), (1, 5), (True, 1)]:
            with self.assertRaises(ValueError):
                bounds(requests, workers)

    def test_corrupt_model_rejected_before_server_or_deserialization(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'model.joblib').write_bytes(b'not a serialized model')
            (root / 'report.json').write_text(json.dumps({'artifact_sha256': '0' * 64,
                'model_version': 'delay-v2', 'release_assessment': {'research_gate_passed': True}}))
            with self.assertRaisesRegex(ValueError, 'Verified research artifact'):
                run(root, 1, 1)

    def test_real_native_http_workflow_uses_and_removes_disposable_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = build_model(15, json.loads(PROTOCOL_PATH.read_text()))
            frame = pd.DataFrame({'carrier': ['AA'] * 500, 'origin': ['JFK'] * 500,
                'destination': ['LAX'] * 500, 'scheduled_departure_hour': ['9'] * 500,
                'scheduled_departure_minute': ['0'] * 500, 'day_of_week': ['1'] * 500})
            with threadpool_limits(limits=2):
                model.fit(frame, [0, 1] * 250)
            joblib.dump(model, root / 'model.joblib')
            digest = hashlib.sha256((root / 'model.joblib').read_bytes()).hexdigest()
            (root / 'report.json').write_text(json.dumps({'artifact_sha256': digest,
                'model_version': 'delay-v2', 'release_assessment': {'research_gate_passed': True}}))
            original = (root / 'model.joblib').read_bytes()
            result = run(root, requests=2, workers=2)
            self.assertTrue(result['passed'])
            self.assertTrue(all(result['checks'].values()))
            self.assertEqual(result['saved_rows_before_cleanup'], 4)
            self.assertEqual(result['warm_prediction_measurement']['requests'], 2)
            self.assertFalse(result['production_ready'])
            self.assertFalse(result['performance_target_assessed'])
            self.assertEqual((root / 'model.joblib').read_bytes(), original)
            serialized = json.dumps(result)
            for private in ['csrf_token', 'password', 'Cookie', 'owner_id', 'run_id', folder]:
                self.assertNotIn(private, serialized)
