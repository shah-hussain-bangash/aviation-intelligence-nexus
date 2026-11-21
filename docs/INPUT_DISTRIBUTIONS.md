# Recorded input distribution comparison

The dashboard's **Compare historical inputs** link opens five descriptive marginal comparisons: reporting carrier, origin, destination, scheduled departure hour and ISO weekday. It compares the January–March 2025 reference cohort with May 2025 and offers scaled paired bars, exact counts/shares, signed percentage-point changes, every-category viewing and a JSON export. All authenticated roles can read the panel. HTTP reads only a pinned public aggregate report; refreshing does not profile the database.

## Actual experiment

The read-only database snapshot covered **1,611,046 reference records and 597,574 May records** in **13.552 seconds**. Each input's counts sum to these populations, matching the frozen delay-v2 model report. Eligible rows follow the dataset builder: official BTS source, completed/non-diverted, observed arrival delay, nonempty flight number and scheduled departure. April is excluded from this comparison.

| Input | Total variation | JS divergence, bits | May records with category absent from reference |
|---|---:|---:|---:|
| Carrier | 0.018851 | 0.000441 | 0 |
| Origin | 0.043310 | 0.004270 | 241 |
| Destination | 0.043847 | 0.004304 | 241 |
| Departure hour | 0.013380 | 0.000270 | 0 |
| ISO weekday | 0.046677 | 0.001754 | 0 |

Weekday shares have the largest total-variation value among these five comparisons. This is a descriptive ranking, not a significance claim, operational warning or explanation of errors. No model was fit, tuned, inferred or changed by this pipeline, and no delay-outcome rate is calculated. May has already been evaluated in earlier experiments; this is a retrospective diagnostic rather than a new held-out evaluation.

The first attempt to read protected private CSV exports could not start and produced no diagnostic report. The delivered experiment uses the restored database. **Matching population counts do not prove identical frozen CSV bytes or record membership.** The public report explicitly records `csv_identity_verified=false`. No file permissions were changed and no inaccessible CSV contents were used.

## Statistics and boundaries

For normalized reference shares `p` and comparison shares `q`, total variation is `0.5 * sum(abs(p-q))`. It ranges from zero for equal marginal shares to one for disjoint support. Jensen–Shannon divergence uses midpoint `m=(p+q)/2` and equals `0.5 * sum(p*log2(p/m) + q*log2(q/m))`, omitting zero terms. It is symmetric, in bits, and also ranges from zero to one. The reported JS metric is divergence, not its square root. No smoothing or sample-size weighting is applied.

The absent-category measure is the fraction of May records whose raw category was absent from the reference. A zero absent-category fraction can coexist with different shares. These categories are not the model's ordinal-encoded or rare-category-collapsed representation. Hours are coarse bins: midnight code 2400 maps to 00, while minute detail is discarded. Weekday 1 is Monday. Joint dependencies and the exact cyclic feature representation are not compared.

There are no confidence intervals, significance tests or chosen alert thresholds. Seasonal schedules, calendar composition and other differences can change marginal shares; this experiment does not establish any causal explanation or model degradation. Eligibility conditions on completed flights with observed outcomes, so these are not full-flight or point-in-time traffic distributions. No live monitoring, UAE transfer or operational acceptance is claimed.

## Reproduction and integrity

Run `python -m ml.input_distributions --database <existing-state.sqlite3> --output .local/new-input-comparison` in an authorized environment that can read the restored database. For Docker, use the container's `/app/.local/active/ain.sqlite3` and choose a new output directory under `/app/.local`. Outputs include the protocol/start record and aggregate report. Existing output directories are rejected. Missing databases are not created. The connection is read-only/query-only, uses one consistent transaction and a cooperative 120-second budget. Fixed SQL expressions, strict category validation and at most 2,000 categories per input bound the calculation. A failure never publishes a final report.

`ml/input_shift_protocol.json` is fingerprint-pinned before the measured database run. The report records that fingerprint, the frozen model report fingerprint and a fingerprint of the feature expressions/eligibility definition. These are reproducibility metadata, not a database snapshot attestation or protected audit. The API checks the fixed report hash, source scope and reconciled counts, shares, distances and unseen mass before serving. It checks population counts against the pinned model report again. It does not reopen the source database or inaccessible CSV files.

Seven Python tests cover mathematical endpoints/symmetry, missing support, eligibility, midnight/weekday handling, invalid categories, no-write aggregation, output/counter mismatch/deadline behavior, recorded arithmetic/file integrity and authenticated viewer/failure behavior. Three Node tests check displayed scope/counts, arithmetic/escaping and the fixed read-only proxy. Five isolated browser scenarios cover desktop, exact 390px mobile, feature/all-category selection, export, outage/invalid-response recovery and session clearing. They use the actual aggregate report with simulated transport and no real account. See `reports/Input_Distributions_Browser.json`.

Representative operational baselines, approved monitoring intervals, owned alert handling, joint/conditional diagnostics, model-performance linkage and production acceptance remain outstanding. All 24 production requirements remain open.
