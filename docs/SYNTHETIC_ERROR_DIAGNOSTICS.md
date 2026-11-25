# Read-only synthetic error diagnostics

25 November 2026. Research only; no airline-quality or production approval.

`ml.synthetic_error_diagnostics` inspects a completed synthetic holdout attempt. Supply the SHA-256 of the retained evaluation receipt, obtained from the earlier evaluation record, rather than silently trusting whatever receipt is currently present:

```powershell
.\.venv\Scripts\python.exe -m ml.synthetic_error_diagnostics <experiment-directory> --receipt-sha256 <recorded-sha256>
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_synthetic_error_diagnostics.py
```

The command prints JSON and returns 0 for verified consistency or 2 for refusal. It does not create files, call the evaluator, create/reset a claim, train/select a model, query a database, or contact a provider. Keep its JSON output in a separate private evidence directory if required. It rereads already evaluated targets solely for descriptive diagnostics; this does not provide a fresh or unused holdout.

It checks the pinned successful receipt, retained attempt identity/policy, frozen protocol/selection, development binding and query-ID separation, exact feature/label bytes, temporal and complete-cohort constraints, coefficient prediction fingerprint and aggregate metrics. The supported sparse transform is reconstructed from the frozen JSON state. Metrics must match the receipt to a tight numeric tolerance; identities and hashes match exactly. Observable input changes during inspection cause refusal. This is not an atomic filesystem snapshot, authenticated provenance or a security boundary against an operating-system owner who can forge all files and the supplied pin.

The report contains record counts, MAE, RMSE and mean **prediction minus actual** error for the overall cohort, each observed origin, and known/unknown origins relative to training categories. Positive signed error means overprediction. Baseline metrics use the original frozen training median. Empty groups have zero records and null metrics, rather than invented zero errors. Groups below 30 records are explicitly flagged `small_cohort`; this descriptive threshold is not a statistical power calculation or privacy guarantee. No confidence intervals, significance claims, promotion decision, new thresholds, hyperparameter ranking, calibration or automatic retuning are produced. No row-level IDs, targets or predictions are emitted.

Tests reconcile weighted cohort MAE/counts, independently calculate an unknown-origin prediction and signed error, verify no fitting or input changes, reject altered files/metrics/claims and failed receipts, and exercise command-line success/refusal. The toy formula shared with development makes synthetic errors unsuitable for estimating real aviation performance. Reviewing diagnostics must not be used to retune against this consumed holdout; any subsequent evaluated experiment needs a separately reviewed data/protocol plan. Physical-flight/group independence, representative authorized data, protected registration, model lifecycle and production qualification remain open.

This change leaves the original delay model, real historical holdout, application state contracts, API, 64 dashboard workspaces and running deployment unchanged. It is stacked on the one-attempt synthetic evaluation change and must be reviewed with that dependency.
