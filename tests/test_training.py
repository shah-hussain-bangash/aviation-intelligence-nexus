from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from ml.prepare_dataset import FEATURES
from ml.train_baseline import build_model, load_split, metrics


class TrainingTests(unittest.TestCase):
    def test_encoder_is_train_only_and_accepts_unknown_categories(self):
        training = pd.DataFrame({feature: ["A", "B"] * 30 for feature in FEATURES})
        model = build_model(1.0)
        model.fit(training, [0, 1] * 30)
        unknown = pd.DataFrame({feature: ["UNSEEN"] for feature in FEATURES})
        probabilities = model.predict_proba(unknown)
        self.assertTrue(np.isfinite(probabilities).all())
        self.assertEqual(probabilities.shape, (1, 2))
        self.assertTrue(all("UNSEEN" not in categories for categories in model.named_steps["encoding"].categories_))
        self.assertEqual(list(model.feature_names_in_), FEATURES)

    def test_metrics_use_declared_threshold_and_confusion_order(self):
        result = metrics(np.array([0, 0, 1, 1]), np.array([.1, .4, .3, .9]), .3)
        self.assertEqual(result["confusion_matrix_labels_0_1"], [[1, 1], [0, 2]])
        self.assertEqual(result["recall"], 1)
        self.assertEqual(sum(row["count"] for row in result["calibration_bins"]), 4)

    def test_modified_dataset_is_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "train.csv"
            path.write_text("modified\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_split(Path(temp), "train", {"splits": {"train": {"sha256": "wrong"}}})
