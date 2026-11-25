# Development-only regression candidate selection

Third new data-science continuation increment, 25 November 2026. A standalone candidate-selection function now fits synthetic development regressors with train-only preprocessing and validation-only selection. It does not read/evaluate a test split, retrain the existing delay model, use its holdout or deploy any candidate.

## Explicit protocol and data boundary

`ml.regression_selection.select_regression(development, declared_protocol)` accepts exactly the prepared-development fields and requires an empty test partition. Extra top-level/partition fields are refused. This rejection occurs before preprocessing or input hashing could read test rows. Training/validation rows still pass the prior preparation/preprocessing provenance, maturity, scope, identity and feature-column checks.

`protocol(...)` declares the experiment ID, source scope, chronological boundaries, arrival-delay target, explicit feature columns, fixed alpha grid `[0.1, 1.0, 10.0]`, validation-MAE selection, smaller-alpha tie-break, training-median baseline and solver settings. A changed metric/grid/policy cannot silently pass this protocol version. A future experiment change requires an explicitly reviewed code/protocol change, not tuning against test results.

The demonstration writes `registered-protocol.json` and the development input **before** invoking candidate fitting, then writes the chosen result to `frozen-selection.json`. These are local, unsigned records in an exclusive fresh directory. They are not a protected central experiment registry, global experiment-ID uniqueness, source authorization or protection from an OS owner editing artifacts. Repeat development runs create new cases and retain their separate evidence.

## Fit and selection

Preprocessing is fitted once on training `X` under the existing encoder/scaler contract. Each Ridge candidate then fits only that transformed training matrix and its training targets. The fixed `lsqr` solver uses tolerance `1e-8` and at most 1,000 iterations. Coefficients, intercept and reported iterations are retained. Iteration counts alone do not independently certify numerical convergence or optimizer optimality.

Candidates predict only the validation matrix. MAE determines selection; RMSE is recorded as an additional error measure. Exact MAE ties choose the smaller alpha. The baseline is the median training target, scored on the same validation rows. Comparison to that baseline is an observed development result, not a production acceptance gate or airline improvement claim.

At least three training rows, two validation rows and nonconstant training targets are required. These permissive research bounds are not adequate production cohort criteria. The inherited 50,000-row/1,000-training-origin limits apply; model fitting has no hard wall-time/resource deadline. Invalid/nonfinite numerical results are refused. Missingness, unseen-origin policy and physical-flight/group disjointness retain their earlier limitations.

The selected JSON state records coefficients in the fitted output-column order and binds the preprocessing-state hash. All candidate validation metrics, protocol/development hashes, training/validation counts and explicit `test_evaluated=false` are retained. The in-memory candidate objects are not serialized with pickle/joblib. This change does not supply a production artifact loader, model registry, inference endpoint, holdout authorization lock or deployment package.

## Synthetic demonstration

```powershell
.\.venv\Scripts\python.exe -m ml.verify_regression_selection
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_regression_selection.py -v
npm.cmd test
```

The host-only command accepts no existing database/input/output path and creates `.local/regression-selection/<case_id>/`. It generates twenty June training rows and eight July validation rows from a declared linear toy formula using synthetic weather/origin features and next-day labels. No test examples are generated. These dates/formula are illustrations, not new airline observations, representative accuracy evidence or an unused real holdout.

Ten demonstration checks cover retained protocol bytes, absence of test rows, cohort/candidate counts, validation-only choice, baseline recording and source stability. A second synthetic development fit changes validation targets and verifies candidate coefficients and preprocessing state stay unchanged, while validation metrics can change. This is fitting-boundary evidence; validation is intentionally used to select among already-trained candidates.

Focused tests inspect the actual `Ridge.fit` targets, reject test/hidden fields before fitting, reject changed protocol policy, verify MAE/RMSE by hand, check minimum/variance guards and confirm the protocol file exists when fits execute. Exact source revision/dirty state, protocol/input/selection byte hashes and selected source hashes are recorded. Previous cases, original experiment sources, historical dataset, frozen model and dashboard remain unchanged.

Real-source approval, representative target/cohort review, protected experiment registration, a genuinely unused chronological evaluation, model lifecycle and release qualification remain open. A selected synthetic regressor is not an airline-ready model, an improvement to the existing system's reported metrics or production readiness.
