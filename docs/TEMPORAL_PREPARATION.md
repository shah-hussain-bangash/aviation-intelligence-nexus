# Point-in-time research split preparation

First new data-science continuation increment, 24 November 2026. Foundation, data-platform and production acceptance requirements remain open. This standalone library prepares chronological examples from availability-time weather features and separately declared arrival-delay labels. It does not fit a model, access the application dataset, read the frozen experiment's rows or improve its reported accuracy.

## Input contract and leakage boundaries

`ml.temporal_preparation.prepare_splits(features, labels, train_start=..., train_end=..., validation_end=..., test_end=..., scope=...)` requires four strictly increasing canonical UTC boundaries. Source scope must be explicitly `synthetic` or `historical_research`, and both feature and label records must match it. Labels and timestamps are caller-declared research facts, not authenticated source evidence.

Feature rows must have exactly the existing availability-time join output fields. The library revalidates timestamps and provenance instead of trusting a cached `matched` flag: observation <= availability <= decision, recorded age equals elapsed observation age, maximum age is a supported integer, and matched measurements are finite numeric values with nonnegative wind. Stale/unavailable representations are also checked. Extra fields, including targets accidentally copied into feature rows, fail admission.

Label rows have exactly `query_id`, `arrival_delay_minutes`, `label_available_at` and `source_scope`. The label value must be finite numeric data; early arrivals may be negative. Label availability must follow that query's decision time. This is an arrival-delay research contract, not a universal event-time rule. A source adapter must establish which completed/non-diverted flights have valid targets, units and trustworthy receipt times; cancellation/diversion eligibility is not inferred here.

Feature query IDs and label IDs must each be unique. Labels without a feature row are refused. Missing labels are permitted as explicit exclusions. Query ID separation does not independently prove distinct physical flights, passengers or aircraft; upstream mapping must prevent hidden duplicate entities or correlated groups when the experiment requires grouped separation.

## Split and maturity policy

Decisions belong to half-open intervals: training `[train_start, train_end)`, validation `[train_end, validation_end)`, and test `[validation_end, test_end)`. The exact lower boundary is included and the upper boundary belongs to the next interval. This is time-based splitting, not random sampling.

Within each interval, a target is usable only if its recorded availability is at or before that interval's ending cutoff. For example, a June training decision whose outcome becomes available in July is excluded from the June training build. It is not silently moved into the validation set. Labels exactly at the ending cutoff are available for that build. Validation/test maturity cutoffs describe when those labels can be evaluated; they do not authorize using them to train or tune an earlier model.

Exclusions have explicit priority: outside the experiment window, weather not matched, missing label, then label not available at that split cutoff. These cohorts are mutually exclusive. Stale/missing weather is excluded without imputation; that complete-case choice can bias the evaluation population and must be reviewed for real data. A downstream trainer must enforce minimum sample/cohort requirements; empty prepared splits are not model approval.

Only `origin`, `temperature_c` and `wind_knots` enter `X`. The arrival-delay target is separate `y`; weather/label times and event ID remain separate provenance. Returned examples are sorted by decision time and query ID. No preprocessing statistics, encoders, parameter selection, threshold tuning or test evaluation are fitted. Downstream training must use only declared `X`, fit preprocessing on training data, freeze selection before a new test evaluation and honour existing holdout policy.

## Reproduce the synthetic preparation

```powershell
.\.venv\Scripts\python.exe -m ml.verify_temporal_preparation
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_temporal_preparation.py -v
npm.cmd test
```

The host-only demonstration accepts no existing database/input/output path and creates a new case under `.local/temporal-preparation/<case_id>/`. Seven generated feature rows and six labels produce one mature example per split and four exclusions: two late labels, one missing-weather example and one missing-label example. The June–August 2025 dates are synthetic illustrations after the frozen historical May test period, not newly acquired independent airline data.

Retained `synthetic-input.json`, `prepared-splits.json` and `report.json` bind exact bytes, source revision/dirty state where available and selected source hashes. The ten demonstration checks include changing a generated test target and confirming training/validation preparations are unchanged. This is a preparation noninterference test, not a model-quality or preprocessing-fit proof. No frozen experiment or its real holdout rows are accessed by the demonstration.

At most 50,000 feature rows and 50,000 labels are admitted. Inputs/results are held in memory; iterables must be trusted and terminate. These are admission bounds, not representative throughput/memory measurements or a hard deadline. All supplied records, including excluded/out-of-window inputs, are validated; malformed future input can reject the whole call. Existing experiment configuration, model files, historical reports, API scoring and dashboard behavior remain unchanged.

An authorized weather/label adapter, checked flight/group identity, measured missingness/cohort coverage, a registered independent experiment, train-only preprocessing and a genuinely unused chronological evaluation are still required before claiming predictive benefit. The original delay-v2 results and already-used holdout remain frozen. This increment does not establish production readiness or complete the data-science phase.
