# BTS flight ingestion

The initial local import contains **539,747 flights** from January 2025 across 14 reporting carriers. These are US domestic records, not Emirates or Etihad data. Source: [official BTS monthly archives](https://transtats.bts.gov/PREZIP/). Schema definitions: [BTS download fields](https://transtats.bts.gov/DL_SelectFields.aspx?QO_fu146_anzr=b0-gvzr&gnoyr_VQ=FGJ).

The raw ZIP (27,108,664 bytes) and local SQLite database stay out of Git. The sanitized measured receipt is `docs/reports/BTS_2025_01_Import.json`. Its archive SHA-256 records the exact downloaded bytes; it is not an independently published BTS checksum.

Download the official archive into `.local/downloads/bts_2025_01.zip`:

https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_1.zip

Then, from the repository root using the configured Python environment:

```powershell
python -m pipelines.import_bts .local/downloads/bts_2025_01.zip --year 2025 --month 1
python -m unittest discover -s tests -v
```

Use `.venv/Scripts/python.exe` instead of `python` when using the isolated setup. The importer streams CSV directly from the ZIP, validates required columns, declared month, airports, carrier, flight number, scheduled time, flags and finite delays. Missing delay values remain NULL. Invalid records or conflicting identities abort the entire import transaction. Exact repeat archives are skipped by hash. Duplicate natural identities with identical stored values are counted; conflicting revisions require review rather than silent replacement. Source URL, hash, period and row counts are stored transactionally in the `imports` table.

The starting schema stores selected fields only; preserve the raw archive for further feature engineering. The local dataset contains 16,312 cancelled and 1,166 diverted flights. There are 15,923 missing departure delays and 17,478 missing arrival delays. These are measured completeness counts, not model errors. Cancellation/diversion and missing targets need an explicit training inclusion policy. Actual delays and other post-event information must not become pre-departure prediction features.

This one-month import proves ingestion. Additional historical months, temporal train/validation/test partitions, data coverage checks and scale benchmarking are required before claiming a large-scale trained system. SQLite is the local foundation; distributed storage and processing are not implemented.
