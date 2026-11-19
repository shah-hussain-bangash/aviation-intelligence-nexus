"""Second, prespecified temporal experiment. May labels are evaluated after selection."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OrdinalEncoder
from threadpoolctl import threadpool_limits

from ml.prepare_dataset import FEATURES, TARGET
from ml.features_v2 import time_features
from ml.train_baseline import metrics, sha256
from services.api.main import ROOT

PROTOCOL_PATH = ROOT / "ml/experiment_v2.json"
PROTOCOL_HASH = "a8f0fa1997933592dd32adef4d2c5536fb42956dd1053f826ffba40352fbb0e6"


def build_model(leaves, protocol):
    transform = ColumnTransformer([
        ("categories", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1,
            encoded_missing_value=-1, max_categories=protocol["max_categories"]), protocol["categorical_features"]),
        ("time", FunctionTransformer(time_features, validate=False),
            ["scheduled_departure_hour", "scheduled_departure_minute", "day_of_week"]),
    ], remainder="drop")
    return Pipeline([
        ("features", transform),
        ("classifier", HistGradientBoostingClassifier(max_leaf_nodes=leaves,
            max_iter=protocol["max_iter"], learning_rate=protocol["learning_rate"],
            min_samples_leaf=protocol["min_samples_leaf"], l2_regularization=protocol["l2_regularization"],
            early_stopping=False, categorical_features=[True] * 3 + [False] * 4,
            random_state=protocol["seed"])),
    ])


def load_split(dataset, name, manifest, protocol):
    path = dataset / f"{name}.csv"
    if sha256(path) != manifest["splits"][name]["sha256"]:
        raise ValueError(f"Hash mismatch: {name}")
    frame = pd.read_csv(path, dtype={feature: str for feature in FEATURES})
    if frame.empty or len(frame) != manifest["splits"][name]["eligible_records"]:
        raise ValueError(f"Row count mismatch: {name}")
    if not frame["flight_date"].str.slice(0, 7).isin(protocol["period_groups"][name]).all():
        raise ValueError(f"Temporal coverage mismatch: {name}")
    if frame[FEATURES + [TARGET]].isna().any().any() or set(frame[TARGET].unique()) != {0, 1}:
        raise ValueError(f"Invalid fields or target classes: {name}")
    if frame["record_key"].duplicated().any():
        raise ValueError(f"Duplicate records: {name}")
    return frame


def gate(results, protocol):
    rule = protocol["research_gate"]
    comparisons = {}
    for name in ("validation", "test"):
        model, prior = results[name]["model"], results[name]["constant_training_prior"]
        comparisons[name] = {
            "auc_pass": model["roc_auc"] >= rule["validation_and_test_min_auc"],
            "log_loss_pass": model["log_loss"] <= prior["log_loss"] * rule["validation_and_test_max_log_loss_ratio_to_training_prior"],
            "brier_pass": model["brier_score"] < prior["brier_score"],
        }
    return {"research_gate_passed": all(all(part.values()) for part in comparisons.values()),
            "comparisons": comparisons, "approved_for_operational_serving": False,
            "reason": "Research gate only; airline transfer, deployment and operational qualification remain unverified"}


def train(dataset, output):
    if output.exists():
        raise ValueError("Experiment output already exists; preserve its frozen result")
    if sha256(PROTOCOL_PATH) != PROTOCOL_HASH:
        raise ValueError("Prespecified protocol changed; create a new experiment")
    protocol = json.loads(PROTOCOL_PATH.read_text())
    manifest = json.loads((dataset / "manifest.json").read_text())
    if (manifest["dataset_version"] != protocol["dataset_version"] or
        manifest.get("period_groups") != protocol["period_groups"] or manifest["features"] != FEATURES or
        manifest["target"] != TARGET):
        raise ValueError("Dataset contract differs from experiment protocol")
    # Reserve the run directory so a later crash cannot silently repeat holdout evaluation.
    output.mkdir(parents=True)
    (output / "started.json").write_text(json.dumps({"protocol_sha256": PROTOCOL_HASH,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "policy": "Do not rerun a failed experiment against May without reviewing whether labels were read"}, indent=2))
    training = load_split(dataset, "train", manifest, protocol)
    validation = load_split(dataset, "validation", manifest, protocol)
    prior = float(training[TARGET].mean())
    best, candidates = None, []
    for leaves in protocol["candidates"]:
        print(f"Fitting {leaves}-leaf boosting on {len(training):,} flights", flush=True)
        model = build_model(leaves, protocol)
        with threadpool_limits(limits=4):
            model.fit(training[FEATURES], training[TARGET])
            probabilities = model.predict_proba(validation[FEATURES])[:, 1]
        result = metrics(validation[TARGET], probabilities, .5)
        candidates.append({"max_leaf_nodes": leaves, "validation": result})
        if best is None or result["log_loss"] < best[0]:
            best = (result["log_loss"], model, probabilities, leaves)
        print(f"April log loss: {result['log_loss']:.6f}", flush=True)
    _, model, probabilities, leaves = best
    from sklearn.metrics import f1_score
    threshold = float(max(np.linspace(.10, .60, 51), key=lambda value:
        f1_score(validation[TARGET], probabilities >= value, zero_division=0)))
    joblib.dump(model, output / "model.joblib", compress=3)
    report = {"model_version": "delay-v2", "algorithm": "categorical histogram gradient boosting",
        "protocol_sha256": PROTOCOL_HASH, "protocol": protocol, "selected_leaf_nodes": leaves,
        "threshold": threshold, "training_records": len(training), "training_delay_prevalence": prior,
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        "dataset_hashes": {name: manifest["splits"][name]["sha256"] for name in protocol["period_groups"]},
        "artifact_sha256": sha256(output / "model.joblib"), "candidates": candidates,
        "validation": {"model": metrics(validation[TARGET], probabilities, threshold),
            "constant_training_prior": metrics(validation[TARGET], np.full(len(validation), prior), threshold)},
        "runtime": {"python": platform.python_version(), "sklearn": sklearn.__version__,
            "pandas": pd.__version__, "numpy": np.__version__, "joblib": joblib.__version__},
        "production_ready": False,
        "limitations": ["US domestic data; no UAE validation", "Historical schedules lack point-in-time snapshots",
            "Conditional on completed non-diverted flights with observed target",
            "No weather inputs; category cap groups rare airports; limited seasonal history",
            "Threshold maximizes validation F1, not operational value",
            "May evaluated once; further tuning requires another untouched holdout"]}
    # Persistent freeze receipt exists before any test labels are loaded.
    (output / "selection_frozen.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Selection frozen: leaves={leaves}, threshold={threshold:.2f}; opening May", flush=True)
    (output / "test_evaluation_started.json").write_text(json.dumps({"utc": datetime.now(timezone.utc).isoformat()}))
    test = load_split(dataset, "test", manifest, protocol)
    with threadpool_limits(limits=4):
        predicted = model.predict_proba(test[FEATURES])[:, 1]
        restored = joblib.load(output / "model.joblib")  # Only this run's locally-created artifact.
        np.testing.assert_allclose(restored.predict_proba(test[FEATURES].iloc[:100])[:, 1], predicted[:100])
    report["artifact_roundtrip_verified"] = True
    report["test"] = {"model": metrics(test[TARGET], predicted, threshold),
        "constant_training_prior": metrics(test[TARGET], np.full(len(test), prior), threshold)}
    report["release_assessment"] = gate(report, protocol)
    report["test_by_carrier"] = {}
    for carrier, indexes in test.groupby("carrier").groups.items():
        indexes = np.asarray(indexes)
        if test.loc[indexes, TARGET].nunique() == 2:
            report["test_by_carrier"][carrier] = metrics(test.loc[indexes, TARGET], predicted[indexes], threshold)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / ".local/datasets/bts-jan-may-2025-v2")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/models/delay-v2")
    args = parser.parse_args()
    report = train(args.dataset, args.output)
    print(json.dumps({"test": report["test"], "assessment": report["release_assessment"]}, indent=2))
