import json
from contextlib import closing
import sqlite3
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from auth_helpers import authenticated_client as TestClient
import joblib
import pandas as pd
from threadpoolctl import threadpool_limits

from ml.train_baseline import sha256
from ml.train_v2 import build_model, PROTOCOL_PATH
from services.api.main import create_app


class PredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = build_model(15, json.loads(PROTOCOL_PATH.read_text()))
        frame = pd.DataFrame({"carrier": ["AA"] * 500, "origin": ["JFK"] * 500,
            "destination": ["LAX"] * 500, "scheduled_departure_hour": ["9"] * 500,
            "scheduled_departure_minute": ["0"] * 500, "day_of_week": ["1"] * 500})
        with threadpool_limits(limits=2):
            cls.model.fit(frame, [0, 1] * 250)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        joblib.dump(self.model, self.root / "model.joblib")
        self.report = {"artifact_sha256": sha256(self.root / "model.joblib"), "model_version": "delay-v2",
                       "release_assessment": {"research_gate_passed": True}}
        self.write_report()
        self.client = TestClient(create_app(self.root / "test.sqlite3", research_model_directory=self.root))
        self.client.__enter__()
        self.payload = {"carrier": "AA", "origin": "JFK", "destination": "LAX",
                        "flight_date": "2025-05-15", "scheduled_departure": "09:00"}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def write_report(self):
        (self.root / "report.json").write_text(json.dumps(self.report))

    def test_real_inference_has_bounds_provenance_and_research_warning(self):
        response = self.client.post("/api/v1/research/predict", json=self.payload)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertAlmostEqual(result["arrival_delay_15_probability"], .5)
        self.assertTrue(result["research_only"])
        self.assertFalse(result["operational_serving_approved"])
        self.assertEqual(result["artifact_sha256"], self.report["artifact_sha256"])
        self.assertGreaterEqual(len(result["warnings"]), 4)
        self.assertEqual(self.client.get("/api/v1/status").json()["flight_records"], 0)

    def test_unknown_code_abstains(self):
        response = self.client.post("/api/v1/research/predict", json={**self.payload, "origin": "DXB"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["fields"], ["origin"])
        self.assertNotIn("arrival_delay_15_probability", response.json())

    def test_invalid_or_extra_fields_are_rejected(self):
        for changes in [{"flight_date": "2026-01-01"}, {"scheduled_departure": "25:00"},
                        {"destination": "JFK"}, {"arrival_delay_minutes": 12}, {"carrier": "<script>"}]:
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post("/api/v1/research/predict", json={**self.payload, **changes}).status_code, 422)

    def test_corrupted_artifact_fails_even_after_cache_was_loaded(self):
        self.assertEqual(self.client.post("/api/v1/research/predict", json=self.payload).status_code, 200)
        with (self.root / "model.joblib").open("ab") as stream:
            stream.write(b"invalid")
        self.assertEqual(self.client.post("/api/v1/research/predict", json=self.payload).status_code, 503)

    def test_failed_gate_prevents_inference(self):
        self.report["release_assessment"]["research_gate_passed"] = False
        self.write_report()
        self.assertEqual(self.client.post("/api/v1/research/predict", json=self.payload).status_code, 503)

    def test_saved_history_and_request_key_replay(self):
        headers = {"Idempotency-Key": str(uuid4())}
        first = self.client.post("/api/v1/research/predict", json=self.payload, headers=headers).json()
        second = self.client.post("/api/v1/research/predict", json=self.payload, headers=headers).json()
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertTrue(second["replayed"])
        self.assertEqual(len(self.client.get("/api/v1/research/history").json()["runs"]), 1)
        changed = self.client.post("/api/v1/research/predict", json={**self.payload,"scheduled_departure":"10:00"}, headers=headers)
        self.assertEqual(changed.status_code, 409)

    def test_failed_calculations_create_no_history(self):
        self.client.post("/api/v1/research/predict", json={**self.payload,"origin":"DXB"})
        self.assertEqual(self.client.get("/api/v1/research/history").json()["runs"], [])
        self.assertEqual(self.client.post("/api/v1/research/predict", json=self.payload, headers={"Idempotency-Key":"bad"}).status_code, 422)

    def test_unavailable_history_prevents_successful_response(self):
        with closing(sqlite3.connect(self.root / "test.sqlite3")) as connection, connection:
            connection.execute("DROP TABLE research_runs")
        self.assertEqual(self.client.get("/api/v1/research/history").status_code, 503)
        response = self.client.post("/api/v1/research/predict", json=self.payload)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("arrival_delay_15_probability", response.json())
