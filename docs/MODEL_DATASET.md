# First chronological model dataset

The local database now holds **1,645,503 flights** from January through March 2025. Data comes from the [official BTS reporting-carrier monthly archives](https://transtats.bts.gov/PREZIP/); it covers US domestic operations, not UAE airlines. Import receipts are stored under `docs/reports/BTS_2025_*_Import.json`.

This milestone prepares data only. No model has been trained, no accuracy is claimed, and no dashboard integration is completed.

## Reproduce

Import each official month using `python -m pipelines.import_bts <archive> --year 2025 --month <month>` before running:

```powershell
python -m unittest discover -s tests -v
python -m ml.prepare_dataset
```

Use the Python interpreter from your configured environment. The dataset is written to `.local/datasets/bts-q1-2025-v1/`, excluded from Git. An existing output version is protected against overwrite; use `--output .local/datasets/<new-version>` when rebuilding. The database is read through a consistent transaction. On failure, temporary dataset output is removed.

## Fixed experiment contract

| Split | Period | Purpose |
|---|---|---|
| Train | January 2025 | Fit preprocessing and model parameters |
| Validation | February 2025 | Choose model settings and decision threshold |
| Test | March 2025 | Evaluate the frozen candidate once |

The binary target is arrival delay of at least 15 minutes, conditional on a non-cancelled, non-diverted flight with an observed arrival delay. Exclusions are applied in that order, then missing/invalid required fields. Missing target values are never converted to on-time labels. These filters define the evaluation population; this model will not predict cancellations or disruption risk for all scheduled flights.

The explicit feature allowlist consists of carrier, origin, destination, flight number, calendar month, day of month, ISO weekday, scheduled departure hour and minute. BTS scheduled time `2400` stays hour 24, minute 0. Actual departure delay, actual arrival delay, cancellation and diversion indicators are not model inputs. `record_key` and `flight_date` are audit metadata, not features. Future training code must select only the declared features and fit encoders/imputers on training data alone, handling unseen categories explicitly.

Each CSV has a SHA-256 in the dataset manifest, alongside source archive hashes and per-split inclusion/exclusion counts. The sanitized manifest is also copied to `docs/reports/BTS_Q1_2025_Dataset.json`; raw rows remain local.

Historical reported schedules are not point-in-time schedule snapshots. Three months do not establish seasonal robustness, Gulf-market transfer or distributed big-data performance. Freeze this experiment contract before model development; keep test labels out of tuning. Further releases should use longer training history and untouched future months.
