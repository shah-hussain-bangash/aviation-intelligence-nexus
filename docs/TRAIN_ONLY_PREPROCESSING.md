# Train-only feature preprocessing

Second new data-science continuation increment, 25 November 2026. A standalone preprocessing function now consumes the point-in-time preparation contract, fits on its training feature rows only, and transforms validation/test rows with the resulting state. It fits preprocessing statistics, **not a predictive model**. Existing delay experiments, used holdout, scoring API and dashboard remain unchanged.

## Fit and transform boundary

`ml.train_preprocessing.fit_training_preprocessor(prepared)` validates the selected preparation structure, chronological row membership, mature labels, declared provenance, unique/disjoint query IDs, counts and explicit model-input columns. It requires nonempty training data. Existing exclusions stay excluded. This is not a reconstruction of raw weather/label sources, full weather-age revalidation or authentication of the prepared artifact. Trustworthy source timestamps and proper preparation remain upstream requirements.

The only model inputs are `origin`, `temperature_c` and `wind_knots`. The function constructs a DataFrame from those `X` fields and invokes scikit-learn `ColumnTransformer.fit` once, on training rows. Targets and provenance never enter that DataFrame. `OneHotEncoder` learns training origins; `StandardScaler` learns training numeric means/population variances/scales. Validation and test are transformed without refitting. Empty future splits return zero-row matrices with the fitted output width.

Unseen future origins produce an all-zero origin one-hot block under `handle_unknown='ignore'`. Counts of those rows are reported for each split. They do not silently add categories or dimensions. This is an explicit representation choice, not evidence that predictions on unseen airports are reliable. A later model/review policy must decide how to handle such cases.

Outputs are normalized to SciPy CSR sparse matrices. At most 50,000 prepared feature identities including exclusions and 1,000 distinct training origins are admitted. Existing declared-row/count limits also apply. These are admission bounds, not a measured throughput/memory claim. Numeric values must be finite and wind nonnegative. Overflow/invalid arithmetic or nonfinite fitted/transformed state is refused rather than passed to a downstream model. No missing-value imputer is fitted; the upstream complete-case weather exclusions still carry potential cohort bias.

The function returns an in-memory fitted transformer, transformed matrices and JSON-compatible metadata. The transformer is mutable Python state: callers must not refit it on future data, and must establish their own registered experiment/artifact lifecycle before use. No pickle/joblib artifact is written or loaded by the demonstration.

## Recorded state and limitations

Metadata records training query IDs, an exact training-feature hash, categories, numeric means/variances/scales, output names, future unknown-origin counts and software versions. A separate full-prepared-input hash binds the input including targets. Changing future targets can change that full-input hash while leaving the training fit-state hash unchanged. The fit-state hash is local consistency evidence, not a signed/authenticated model artifact or a guarantee across arbitrary library versions.

The metadata explicitly separates `preprocessor_fitted=true` from `predictive_model_trained=false`, and leaves input authentication/point-in-time recomputation/production readiness false. Selected prepared-provenance checks do not independently prove physical-flight/group disjointness, actual meteorology, original receipt times, target eligibility or source rights. Minimum real cohort/variance criteria, metrics and operational decision criteria remain future experiment requirements.

## Reproduce the synthetic noninterference checks

```powershell
.\.venv\Scripts\python.exe -m ml.verify_train_preprocessing
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_train_preprocessing.py -v
npm.cmd test
```

The host-only command accepts no existing database/input/output path. It creates a fresh case under `.local/train-preprocessing/<case_id>/`, generating point-in-time feature examples and labels with explicit synthetic scope. Two training rows have temperatures 20/30 and winds 5/15, so fitted means are 25/10 and scales 5/5. Training origin is `AAA`; validation/test use unseen synthetic origins `BBB`/`CCC`.

Eight feature examples and seven labels prepare into two training, one validation and one test example plus four exclusions. The verifier changes future features and targets, fits again using the same training rows, and confirms the fit-state signature and training matrix are unchanged. This is a synthetic training-boundary test; it is not a new real-data model experiment or performance evaluation.

The case retains `synthetic-prepared.json`, `preprocessing-state.json`, `sparse-matrices.json` and a report with exact byte hashes and source revision/dirty state where available. Sparse output is represented as shape/data/indices/indptr arrays, not expanded dense datasets. Existing cases are never overwritten. Errors use a fixed private-safe code. Ten demonstration checks and focused tests cover expected scaling, unseen categories, future/target noninterference, exact fit inputs, empty future splits, invalid fields/labels/counts and numerical overflow.

Real-source approval, missingness/group/cohort analysis, a registered independent experiment, a fitted predictive objective, genuinely unused chronological evaluation, model lifecycle and deployment qualification remain open. Neither this implementation nor its synthetic results establish predictive improvement or production readiness. Daily `main` synchronization also remains subject to its separate Desktop Commander/main-branch policy.
