# Portable synthetic scoring bundle

25 November 2026. Local research only; no API, dashboard or deployment change.

The bundle exports the previously selected synthetic regressor after receipt-bound diagnostics pass. It contains only the supported JSON categories, means/scales, coefficients, intercept, fixed baseline and provenance hashes. It excludes development/holdout rows, query IDs, target files and candidate models. The artifact remains private, outside Git; it is not an authorized airline model.

```powershell
.\.venv\Scripts\python.exe -m ml.synthetic_model_bundle export <experiment> <new-bundle.json> --receipt-sha256 <recorded-evaluation-sha256>
.\.venv\Scripts\python.exe -m ml.synthetic_model_bundle score <bundle.json> <synthetic-features.json> --bundle-sha256 <exported-bundle-sha256>
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_synthetic_model_bundle.py
```

Export requires existing completed diagnostics and rechecks observed evidence before exclusive output creation. The destination must be outside the experiment and must not exist. It does not reset an attempt or replace an artifact. A failed filesystem write may leave a partial destination; there is no automatic cleanup or power-loss durability guarantee. Select a reviewed new path after investigating a failed export.

Scoring requires the explicit raw bundle hash and exact supported schema/state fingerprint. It validates finite coefficients, strictly positive scales, feature layout and synthetic feature provenance. It accepts 1–1,000 unique, matched feature rows with no label fields. Unknown origins use the frozen all-zero one-hot representation and are counted. No fitting, selection, database or provider access occurs. Scoring does not require the original experiment directory or target files. Returned predictions carry the bundle/state/receipt identities, synthetic scope and `production_ready:false`; the baseline is a fixed training median. This is delay-minutes regression, not delay-event probability or calibration.

Tests verify exact prediction fingerprint parity with the prior synthetic evaluation, scoring after removing a disposable source experiment, unknown-origin arithmetic, input limits, invalid scopes/labels, altered/re-pinned malformed bundles, receipt refusal, no-overwrite policy and actual export/scoring CLI behavior. Retained synthetic evidence is inspected without changing it. Computing parity on already consumed toy rows is artifact execution evidence, not another independent model evaluation.

Hashes provide consistency, not artifact origin authentication. An OS owner can replace both a file and supplied pin; no signed registry, protected promotion, general model sandbox, managed loader, automated rollback or service is implemented. Production readiness, representative real data, independent quality evaluation and lifecycle ownership remain open. Never use the toy score as an airline operational recommendation.
