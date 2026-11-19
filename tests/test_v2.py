import json
import unittest

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from ml.features_v2 import time_features
from ml.prepare_dataset import validate_groups
from ml.train_v2 import PROTOCOL_PATH, PROTOCOL_HASH, build_model, gate
from ml.train_baseline import sha256


class V2Tests(unittest.TestCase):
    def test_protocol_hash_and_temporal_boundaries(self):
        self.assertEqual(sha256(PROTOCOL_PATH), PROTOCOL_HASH)
        validate_groups(json.loads(PROTOCOL_PATH.read_text())["period_groups"])
        with self.assertRaises(ValueError):
            validate_groups({"train": ["2025-01"], "validation": ["2025-01"], "test": ["2025-03"]})
        with self.assertRaises(ValueError):
            validate_groups({"train": ["2025-01"], "validation": ["2025-03"], "test": ["2025-04"]})

    def test_midnight_cyclic_features(self):
        frame = pd.DataFrame({"scheduled_departure_hour": ["24", "0"],
            "scheduled_departure_minute": ["0", "0"], "day_of_week": ["1", "1"]})
        values = time_features(frame)
        np.testing.assert_allclose(values[0], values[1])
        self.assertEqual(values.shape, (2, 4))

    def test_unseen_airports_and_excluded_inputs(self):
        protocol = json.loads(PROTOCOL_PATH.read_text())
        frame = pd.DataFrame({"carrier": ["AA"] * 500, "origin": ["JFK"] * 500,
            "destination": ["LAX"] * 500, "scheduled_departure_hour": ["9"] * 500,
            "scheduled_departure_minute": ["0"] * 500, "day_of_week": ["1"] * 500,
            "arrival_delay_minutes": [999] * 500})
        model = build_model(15, protocol)
        with threadpool_limits(limits=2):
            model.fit(frame, [0, 1] * 250)
            before = model.predict_proba(frame.iloc[:1])
            frame["arrival_delay_minutes"] = -999
            after = model.predict_proba(frame.iloc[:1])
            np.testing.assert_allclose(before, after)
            frame.loc[0, "origin"] = "UNKNOWN"
            self.assertTrue(np.isfinite(model.predict_proba(frame.iloc[:1])).all())

    def test_gate_requires_validation_and_test_improvement(self):
        protocol = json.loads(PROTOCOL_PATH.read_text())
        result = {name: {"model": {"roc_auc": .65, "log_loss": .4, "brier_score": .1},
            "constant_training_prior": {"log_loss": .5, "brier_score": .15}} for name in ("validation", "test")}
        self.assertTrue(gate(result, protocol)["research_gate_passed"])
        result["test"]["model"]["log_loss"] = .51
        self.assertFalse(gate(result, protocol)["research_gate_passed"])
        self.assertFalse(gate(result, protocol)["approved_for_operational_serving"])
