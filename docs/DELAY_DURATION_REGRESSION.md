# Delay Duration Regression

Select **Inspect duration regression** on the signed-in dashboard. This new offline experiment estimates nonnegative arrival-delay minutes, separately from the existing delay-15 probability classifier. The dashboard compares April/May errors with mean and median baselines, exposes signed residual counts and severe-delay errors, and exports the measured evaluation. **The model failed its preset research check and duration inference is not deployed.** The existing classifier, research predictor, threshold, credentials and 64 workspaces remain unchanged.

## Frozen question and data

`ml/duration_protocol.json` was written and hash-frozen before model fitting or this experiment's target queries. Its canonical UTF-8/LF SHA-256 is `814b217e92070cb990f9239804fdca39c768e6a1849f5653fac74c1c36b473f7`. The target is `max(0, arrival_delay_minutes)` with no upper clipping. Early/on-time arrivals therefore have a zero target. Only completed, non-diverted official BTS flights with observed arrivals are eligible. This conditional task does not estimate cancellation/diversion risk or unconditional disruption duration.

The pipeline uses a read-only/query-only SQLite connection and one consistent snapshot, records the five monthly import hashes/counts and exports private, byte-hashed split CSVs. It checks exact eligible counts, unique keys, date boundaries, schedule syntax, finite targets and feature vocabulary. The public record contains aggregate statistics and hashes, not flight rows, prediction vectors, account data or local paths. Recorded import metadata is lineage, not a fresh archive/license/source-truth verification. Database bytes are not claimed globally immutable; the experiment itself issues no source writes, and its CSV/artifact hashes were rechecked.

| Split | Historical period | Eligible rows |
| --- | --- | ---: |
| Training | January–March 2025 | 1,611,046 |
| Validation | April 2025 | 577,730 |
| Temporal test | May 2025 | 597,574 |
| Total | Five months | 2,786,350 |

These counts align with the earlier eligibility audit of the 2,835,101-row official release. This is a newly constructed duration dataset with its own CSV fingerprints; count agreement does not prove identity with the earlier classification CSVs. All five months have already appeared in prior project analysis. May is a model-specific frozen temporal benchmark here, not a globally untouched holdout or proof of prospective generalization. Reported schedules are not point-in-time schedule snapshots.

## Model and evaluation boundary

One prespecified Scikit-learn histogram gradient boosting regressor uses squared-error loss, 15 maximum leaves, 80 iterations, learning rate 0.08, 200 minimum leaf samples, L2 regularization 10 and seed 42. Early stopping is disabled, so no random validation subset is created. Categories for carrier/origin/destination are learned on training only, capped at 200 with explicit unknown handling. Existing departure-time/weekday sine-cosine transformations are reused. Arrival/departure outcomes, cancellation/diversion flags, flight number, dates, month and day-of-month are excluded from model inputs. Negative model estimates are clipped to zero.

The constant training mean is **15.0413545 minutes**, and the training median is **0 minutes**. No test labels determine either baseline. The model is fit once on January–March. Its artifact, training/April split identities, baselines and full April evaluation are saved in an immutable-by-workflow `freeze.json` before the first May target query. May is then evaluated once. No hyperparameter search, post-May retuning, calibration, replacement of another model or deployed duration endpoint occurs. A new output directory is required, and failed/started runs are retained. A harmless deprecated Pandas weekday alias observed during execution was replaced with its equivalent supported alias; the fitted model/results were preserved and May was not reevaluated.

Squared-error estimation targets a conditional mean; absolute-error estimation instead targets a conditional median. Both evaluation views matter for this zero-heavy, long-tailed target. See the official [regression metric guidance](https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics) and [histogram regressor documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html). This model was not optimized for MAE, and a small RMSE improvement must not conceal a weaker result versus the median baseline.

## Observed negative result

| Period | Estimator | RMSE, min | MAE, min | R² |
| --- | --- | ---: | ---: | ---: |
| April | Frozen model | 49.7324 | 21.0837 | 0.009276 |
| April | Training mean | 49.9670 | 21.7089 | -0.000092 |
| April | Training median | 52.0437 | 14.5630 | -0.084953 |
| May | Frozen model | 55.6693 | 23.1916 | 0.014770 |
| May | Training mean | 56.1718 | 23.9840 | -0.003097 |
| May | Training median | 58.9526 | 18.1625 | -0.104871 |

The preset check requires at least 1% lower RMSE than the training-mean baseline in **both** periods. Measured reductions were only **0.4694% in April** and **0.8946% in May**; the check failed in both periods. MAE was worse than the zero-valued training median in both periods. R² is not an accuracy percentage. These results do not qualify the model for deployment or establish airline value.

Overall May bias, defined as predicted minus actual, was **-3.2716 minutes**. Among **52,142 observed May delays of at least 60 minutes**, model MAE was **124.5464 minutes** and bias **-124.5438 minutes**. This severe-delay group is defined retrospectively using outcomes; the model does not identify that group prospectively. May's largest retained target was 3,241 minutes. Extreme outcomes influence RMSE, and aggregate bias can hide severe underprediction. There are no uncertainty intervals, significance tests or individual reliability claims.

The complete source run, including split queries/exports, fit, scoring and final file checks, took **46.361 seconds** on this workstation. This is one local runtime, not a capacity or distributed-processing benchmark. Private model/CSV/freeze byte checks passed after execution; the artifact identity and April evidence match the pre-May receipt. The negative result is retained in `reports/Delay_Duration_v1.json`. No subsequent May fit/tuning/evaluation was performed in this milestone. Improving the model requires a separately specified experiment and a genuinely new evaluation period rather than repeatedly selecting against this May result.

## API, UI and verification

`GET /api/v1/research/duration-evaluation` permits signed-in viewers, researchers and admins to read fixed, size-bounded aggregate evidence. It verifies report/protocol fingerprints, dataset populations, error arithmetic, R², baseline relationships, residual totals, severe-delay bounds and the failed/passed check against the actual numbers. It loads no model, executes no inference and issues no flight query. Missing/altered evidence returns a sanitized 503. Anonymous requests receive 401, query overrides 422 and the proxy rejects writes/unrecognized paths while stripping unrelated cookies.

The dashboard switches April/May and RMSE/MAE comparisons. Charts start at zero and include exact values; full tables support horizontal scrolling on mobile. The severe-delay group, excluded populations and negative result remain visible. Export preserves the full aggregate, selected period/metric and explicit research/non-deployment scope. Refresh failure clears old results and disables selectors/export; session changes abort pending requests and invalidate late responses. This component QA is not a complete accessibility or security qualification.

Eight new Python tests cover the frozen feature/protocol boundary and unknown categories, read-only SQL/eligibility/midnight/negative-target handling, regression arithmetic/undefined or negative R², freeze-before-May ordering, source/output guards, false-success rejection, cross-platform evidence integrity and authenticated read/failure behavior. Three Node tests verify baseline/severe-error rendering, count/metric consistency and the fixed proxy. Seven isolated browser cases use actual recorded aggregates with simulated transport: desktop, 390px mobile, period/metric/export, tampered success, outage recovery and late session clearing/replacement. No real user session or duration inference is used for browser QA. See `reports/Duration_Regression_Browser.json`. The full Windows suite has **346 tests: 265 Python and 81 Node**.

The executable source is `python -m ml.duration --database .local/ain.sqlite3 --output .local/experiments/new-reviewed-duration-run`. Use a new private output directory, preserve receipts and explicitly review any further target evaluation; rerunning does not create a fresh holdout. Only the sanitized aggregate is published. This adds SQL/Pandas/NumPy processing, regression and temporal evaluation evidence to the portfolio; it does not complete cloud/MLOps, Databricks or airline operational acceptance. All 24 production requirements remain open.
