"""Train on January, select with February, and evaluate March once."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import tempfile
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss,
    confusion_matrix, f1_score, log_loss, precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.prepare_dataset import FEATURES, PERIODS, TARGET
from services.api.main import ROOT


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_split(dataset, name, manifest):
    path = dataset / f"{name}.csv"
    if sha256(path) != manifest["splits"][name]["sha256"]:
        raise ValueError(f"Dataset hash mismatch: {name}")
    frame = pd.read_csv(path, dtype={feature: str for feature in FEATURES})
    if len(frame) != manifest["splits"][name]["eligible_records"] or frame.empty:
        raise ValueError(f"Unexpected row count: {name}")
    if frame[FEATURES + [TARGET]].isna().any().any():
        raise ValueError(f"Missing training fields: {name}")
    if not frame["flight_date"].str.startswith(PERIODS[name] + "-").all():
        raise ValueError(f"Unexpected temporal coverage: {name}")
    if frame["record_key"].duplicated().any() or set(frame[TARGET].unique()) != {0, 1}:
        raise ValueError(f"Invalid identities or classes: {name}")
    return frame


def build_model(c):
    return Pipeline([
        ("encoding", OneHotEncoder(handle_unknown="ignore", min_frequency=20, dtype=np.float64)),
        ("classifier", LogisticRegression(C=c, solver="liblinear", max_iter=300, random_state=42)),
    ])


def metrics(y, probabilities, threshold):
    predicted = probabilities >= threshold
    bins = []
    for index in range(10):
        mask = (probabilities >= index / 10) & (
            probabilities <= 1 if index == 9 else probabilities < (index + 1) / 10)
        if mask.any():
            bins.append({"bin": index, "count": int(mask.sum()),
                         "mean_probability": float(probabilities[mask].mean()),
                         "observed_rate": float(np.asarray(y)[mask].mean())})
    return {"records": len(y), "delay_prevalence": float(np.mean(y)),
            "roc_auc": float(roc_auc_score(y, probabilities)),
            "average_precision": float(average_precision_score(y, probabilities)),
            "log_loss": float(log_loss(y, probabilities, labels=[0, 1])),
            "brier_score": float(brier_score_loss(y, probabilities)),
            "accuracy": float(accuracy_score(y, predicted)),
            "precision": float(precision_score(y, predicted, zero_division=0)),
            "recall": float(recall_score(y, predicted, zero_division=0)),
            "f1": float(f1_score(y, predicted, zero_division=0)),
            "confusion_matrix_labels_0_1": confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
            "calibration_bins": bins}


def train(dataset, destination):
    if destination.exists():
        raise ValueError("Model version already exists; choose a new output directory")
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    if manifest["features"] != FEATURES or manifest["target"] != TARGET:
        raise ValueError("Dataset contract mismatch")
    training = load_split(dataset, "train", manifest)
    validation = load_split(dataset, "validation", manifest)
    prior = float(training[TARGET].mean())
    best = None
    candidates = []
    for c in (0.1, 1.0):
        model = build_model(c)
        print(f"Fitting logistic regression C={c} on {len(training):,} January flights", flush=True)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model.fit(training[FEATURES], training[TARGET])
        probabilities = model.predict_proba(validation[FEATURES])[:, 1]
        loss = float(log_loss(validation[TARGET], probabilities, labels=[0, 1]))
        candidates.append({"C": c, "validation_log_loss": loss,
                           "iterations": int(model.named_steps["classifier"].n_iter_.max())})
        if best is None or loss < best[0]:
            best = (loss, model, probabilities, c)
    _, model, probabilities, chosen_c = best
    # Demonstration F1 policy; not an airline cost/capacity decision threshold.
    threshold = float(max(np.linspace(0.10, 0.60, 51),
                          key=lambda t: f1_score(validation[TARGET], probabilities >= t, zero_division=0)))
    report = {
        "model_version": "delay-baseline-v1", "algorithm": "one-hot logistic regression",
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        "dataset_hashes": {name: manifest["splits"][name]["sha256"] for name in PERIODS},
        "features": FEATURES, "target": TARGET, "selected_C": chosen_c,
        "selection_policy": "Minimum February log loss among C=0.1,1.0; train preprocessing on January only",
        "threshold": threshold, "threshold_policy": "Maximum February F1 over 0.10..0.60 by 0.01; demo policy only",
        "training_records": len(training), "training_delay_prevalence": prior,
        "candidates": candidates,
        "validation": {"model": metrics(validation[TARGET], probabilities, threshold),
                       "constant_training_prior": metrics(validation[TARGET], np.full(len(validation), prior), threshold)},
        "runtime": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                    "pandas": pd.__version__, "numpy": np.__version__, "joblib": joblib.__version__},
        "production_ready": False,
        "limitations": ["US domestic Q1 2025 only; not a UAE airline model",
                       "Conditional on completed non-diverted flights with observed target",
                       "No point-in-time schedule snapshots or weather features",
                       "No operational threshold, prospective trial or airline business impact established",
                       "No deployment, authorization, monitoring or failure recovery qualification",
                       "March is now an evaluated holdout; future tuning requires a fresh holdout"],
    }
    print(f"Frozen C={chosen_c}, threshold={threshold:.2f}; evaluating March once", flush=True)
    test = load_split(dataset, "test", manifest)
    test_probabilities = model.predict_proba(test[FEATURES])[:, 1]
    report["test"] = {"model": metrics(test[TARGET], test_probabilities, threshold),
                      "constant_training_prior": metrics(test[TARGET], np.full(len(test), prior), threshold)}
    report["release_assessment"] = {
        "approved_for_serving": False,
        "assessment_type": "retrospective baseline review; not a preregistered release qualification",
        "test_log_loss_beats_constant_prior": report["test"]["model"]["log_loss"] < report["test"]["constant_training_prior"]["log_loss"],
        "test_brier_beats_constant_prior": report["test"]["model"]["brier_score"] < report["test"]["constant_training_prior"]["brier_score"],
        "reason": "Research artifact only; requires improved prospective validation and operational qualification",
    }
    report["test_by_carrier"] = {}
    for carrier, indexes in test.groupby("carrier").groups.items():
        indexes = np.asarray(indexes)
        if test.loc[indexes, TARGET].nunique() == 2:
            report["test_by_carrier"][carrier] = metrics(test.loc[indexes, TARGET], test_probabilities[indexes], threshold)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="model-", dir=destination.parent))
    try:
        artifact = staging / "model.joblib"
        joblib.dump(model, artifact, compress=3)
        restored = joblib.load(artifact)  # Load only our own freshly-created trusted artifact.
        np.testing.assert_allclose(restored.predict_proba(test[FEATURES].iloc[:100])[:, 1], test_probabilities[:100])
        report["artifact_sha256"] = sha256(artifact)
        report["artifact_roundtrip_verified"] = True
        (staging / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / ".local/datasets/bts-q1-2025-v1")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/models/delay-baseline-v1")
    args = parser.parse_args()
    result = train(args.dataset, args.output)
    print(json.dumps({"model_version": result["model_version"], "test": result["test"]}, indent=2))
