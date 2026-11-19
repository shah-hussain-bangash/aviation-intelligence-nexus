# Second delay experiment

The fixed protocol is `ml/experiment_v2.json`. Its SHA-256 was recorded before downloading or evaluating April/May data:

`a8f0fa1997933592dd32adef4d2c5536fb42956dd1053f826ffba40352fbb0e6`

The training script rejects a changed protocol. This is a local prespecification record, not an independent external preregistration.

## Design

- Training: January–March 2025. March is now allowed in training because a new future holdout replaces it.
- Validation: April 2025, used for model selection and the demonstration threshold.
- Test: May 2025, read for evaluation after model selection is frozen.
- Target and inclusion policy: arrival delay at least 15 minutes among completed, non-diverted flights with observed arrival delay.
- Candidates: categorical histogram gradient boosting with 15 or 31 leaves, 120 iterations, learning rate 0.08, minimum leaf size 200, L2 penalty 10, seed 42.
- Inputs: carrier, origin, destination, sine/cosine of scheduled departure time and weekday. Calendar month, exact day of month and flight number are dropped to reduce reliance on dates or identities that may not generalize. This rationale is a hypothesis, not a measured explanation of v1's failure.
- Category vocabulary: fit on training only, capped at 200 codes per categorical feature; unseen values use the missing-value code. No target encoding.
- Selection: lowest April log loss. No random early-stopping partition and no refit after selection.
- Threshold: best April F1 on 0.10–0.60 grid, step 0.01. This is not an airline cost or resource-capacity decision rule.

The prespecified research gate requires both April and May ROC-AUC at least 0.60, log loss at least 1% lower than the constant training-prior comparator, and lower Brier score. Passing it permits further research demonstration only. It cannot approve operational serving or production readiness.

## Measured result

The database contains 2,835,101 records from January through May 2025. The eligible split counts are 1,611,046 training, 577,730 validation and 597,574 testing. The 15-leaf candidate was selected, with demonstration threshold 0.17.

| Metric | April model | April prior | May model | May prior |
|---|---:|---:|---:|---:|
| ROC-AUC | 0.6355 | 0.5000 | 0.6506 | 0.5000 |
| Average precision | 0.2785 | 0.1966 | 0.3465 | 0.2360 |
| Log loss | 0.4781 | 0.4957 | 0.5261 | 0.5511 |
| Brier score | 0.1528 | 0.1580 | 0.1733 | 0.1818 |

All prespecified research comparisons passed. May log loss is about 4.53% lower than its constant-prior comparator. This is a within-May comparison; v1's March metrics are not a matched test comparison with v2.

At threshold 0.17, May precision is 30.22%, recall 74.21%, F1 0.4295 and accuracy 53.46%. There are 104,667 true alerts and 241,732 false alerts. Always predicting on time would yield 76.40% accuracy; accuracy alone is not the selection criterion. The high alert rate is unsuitable for unqualified operational use. Predicted probabilities also understate delay frequency in several May calibration bins. No further changes were made using these test observations. Future calibration or threshold work needs new validation/test periods.

Research suitability is **passed**; operational and production approval remain **false**. The v1 artifact, its report and its original Q1 dataset remain unchanged.

## Reproduction details

Import official April and May archives using `pipelines.import_bts`. Call `ml.prepare_dataset.prepare` with the protocol's period groups and dataset version to build `.local/datasets/bts-jan-may-2025-v2`. The sanitized dataset manifest is `docs/reports/BTS_Jan_May_2025_Dataset_v2.json`. Dataset files and all model artifacts stay out of Git.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ml.train_v2
```

Do not rerun this experiment once May has been evaluated. The output directory is reserved at startup and preserved after failures to prevent silent repeated test evaluation. A freeze receipt containing selected parameters, threshold, source-data hashes and artifact hash is saved before May labels are loaded. The completed report is `.local/models/delay-v2/report.json`, mirrored in `docs/reports/Delay_v2.json`. API report: `/api/v1/models/delay-v2/report` after restarting the local service.

The legacy v1 report is preserved at `/api/v1/model/report`. Neither endpoint serves predictions. The serialized transformer uses an importable module path, and artifact reload is verified. Only locally-created, trusted artifacts may be loaded with joblib.

## Limits

Five months of US domestic historical data cannot establish seasonal robustness, point-in-time availability of schedules, UAE airline transfer, airline business benefit or distributed data-processing performance. Weather, live schedules, airport congestion and aircraft rotations are absent. Carrier slices and calibration bins are diagnostics; no statistical significance or prospective reliability is claimed. A later experiment needs a new untouched future test period.

Method references: [scikit-learn histogram boosting](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html), [categorical encoder](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OrdinalEncoder.html).
