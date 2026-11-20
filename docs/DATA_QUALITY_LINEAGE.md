# Data quality and lineage

Select **Data quality and lineage** on the signed-in dashboard. The panel serves a pinned, dated aggregate audit of the actual January–May 2025 BTS records. It is a recorded structural audit, not a live lakehouse or database-health view. No account credentials, existing research records or model artifacts are changed, and all 64 workspaces remain.

## Actual audit and coverage

The final read-only monthly SQL audit observed 2,835,101 official flight records, all within the five audited months, with zero detected field/key issue occurrences and zero duplicate stored identifiers. Five recorded archive entries reconciled to the monthly row counts. Its measured runtime was 16.089 seconds in the local Docker environment. This is one bounded local observation, not a capacity qualification.

| Month | Stored records | Eligible arrivals | Cancelled exclusion | Diverted exclusion |
| --- | ---: | ---: | ---: | ---: |
| January | 539,747 | 522,269 | 16,312 | 1,166 |
| February | 504,884 | 496,476 | 7,405 | 1,003 |
| March | 600,872 | 592,301 | 6,923 | 1,648 |
| April | 583,950 | 577,730 | 4,914 | 1,306 |
| May | 605,648 | 597,574 | 6,344 | 1,730 |

The missing/invalid modelling-exclusion count was zero in each audited month. The 2,786,350 eligible arrivals reconcile by count to the frozen dataset populations: 1,611,046 training (January–March), 577,730 validation (April), and 597,574 test (May). This does not prove identical row contents, original CSV byte hashes, source truth or current database state. No model was fitted, scored, selected or recalibrated.

An initial all-period grouped/distinct aggregation exceeded the container's temporary-storage limit and returned no audit report. The successful implementation processes one month at a time within one consistent read transaction, reducing the temporary working set. The failed-attempt directory and observed error remain separate; no source data was written and no failed result is represented as a pass.

## Checks and modelling exclusions

The SQL checks date structure/calendar round-trip, carrier/airport code syntax, canonical flight number, scheduled departure format (including valid source code 2400), binary flags, numeric/finite delay values, reconstructed record identifiers and stored identifier uniqueness within each month. Field issue counts may overlap on a record; they are not a distinct bad-row count. Unknown carrier/airport business meaning and source-value truth are not verified.

Missing delays are allowed in storage. Modelling cohorts reproduce the existing builder's exclusion priority: cancelled first, diverted second, missing/invalid flags or required modelling fields third, then eligible observed arrivals. Structural failures are separately flagged; the audit does not build a dataset or override model acceptance. Other-source records are excluded and reported. Official records outside the fixed window remain unprofiled and prevent a complete passing audit. Invalid official dates are counted across the source.

Import reconciliation checks valid archive SHA-256 syntax, the recorded official source URL pattern, non-negative integer counts and `rows_read = rows_inserted + duplicate_rows`. Valid recorded inserted-row totals are compared to stored monthly counts. Invalid metadata is counted without echoing arbitrary URLs/values. The audit does not open archive files, re-hash them, download anything or prove source permissions. An archive hash is recorded lineage metadata, not an independent attestation.

## Operator reproduction and bounds

`pipelines.audit_quality` uses an existing database in read-only/query-only mode, one SQLite snapshot, a one-second lock wait, a cooperative 120-second query/processing budget and at most 1,000 import entries. It emits aggregates only. Missing files are not created. Output must be a new private directory under `.local`; a reserved started receipt is preserved after failure and prior outputs are never overwritten.

For native state, with its database accessible:

```powershell
.\.venv\Scripts\python.exe -m pipelines.audit_quality --output .local/audits/new-bts-check
```

For the deployed Docker state:

```powershell
docker compose exec -T api python -m pipelines.audit_quality --output /app/.local/audits/new-bts-check
```

Choose a new output name each time. The actual development check executed the same audit source against the deployed database and captured only aggregate JSON. Its public result is `reports/BTS_Data_Quality.json`; the query fingerprint identifies the fixed aggregate SQL recipe. Re-auditing does not automatically replace published evidence. Review new scope/results before changing the pinned report and readiness fingerprints.

## Read-only API and dashboard

GET `/api/v1/research/data-quality` permits authenticated viewers, researchers and administrators. It reads only the size-bounded pinned public audit and frozen dataset reports, validates their fingerprints and recomputes count/field/cohort/import accounting. It performs no live flight SQL, artifact loading or model call. Missing/altered evidence returns HTTP 503 without results; anonymous access is denied and the fixed proxy rejects writes/subpaths.

The dashboard offers monthly checks/lineage details, all-month coverage/exclusion counts, frozen-population count alignment and JSON export. Refresh verifies the recorded report; it does not rerun the audit or update its audit date. Input selection preserves the full five-month report and labels the selected month in the export. Failure/session changes clear prior figures, controls and export state, with late responses ignored. Local file fingerprints are not protected auditing or independent acceptance.

## Verification and remaining limits

The full Windows suite passes 254 tests (200 Python, 54 Node); Linux skips the Windows DPAPI provider case. New cases verify read-only byte preservation on a temporary database, cohort priority, midnight departures, invalid fields/dates/infinite delays, out-of-window coverage, missing/mismatched/private import metadata, failed output preservation, budgets, pinned evidence/line endings, false-pass rejection, source query fingerprint, model-population accounting, authentication and safe errors. Node checks cover rendering, inconsistent counts/conclusions, escaped text and proxy restrictions.

Four isolated browser component cases pass: desktop 1280, exact mobile 390, outage/recovery and session clearing with late responses. They use the actual aggregate audit through simulated transport, without a real user account. Month selection, export and screenshots were inspected. See `reports/Data_Quality_Dashboard.json`.

Zero detected issues apply only to these checks on this recorded snapshot. They do not establish complete data correctness, rights review, live freshness, UAE transfer, distributed processing, incremental ingestion, quarantine/replay, independent governance or production readiness. All 24 production requirements remain open.
