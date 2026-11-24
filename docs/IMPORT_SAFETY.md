# Replay-safe bounded flight ingestion

First new local data-platform increment, 24 November 2026. Foundation work remains incomplete, including deployment-dependent HTTPS, managed identity and protected audit storage. This change hardens the existing historical importer and adds a synthetic drill; it neither imports external data nor changes the primary deployment by itself.

## What changed

Previously the importer hashed a pathname and reopened it for parsing, so a changed file could be parsed under an earlier hash. It now copies the input once to a private temporary file while computing SHA-256, verifies the captured bytes, and parses that same owned copy. Observable file identity/size/modification changes during capture are rejected. Windows creation/change timestamps are not compared across pathname and handle queries; the content hash binds the actual private copy.

The original pathname may change **after** capture. That does not change the consumed copy or its ledger hash. Preserve an authorized retained input/preflight snapshot if the archive must remain inspectable later; the temporary import copy is closed and removed, not a new long-term provenance archive. These checks are not source authentication or resistance to a privileged filesystem owner.

The replay lookup and every flight/ledger write now share one `BEGIN IMMEDIATE` writer transaction. Concurrent small-fixture replays commit one batch and return `already_imported` for the other callers. Identical duplicates retain the existing record; conflicting payloads require review and roll back the entire attempted batch. An invalid later record cannot leave earlier rows from that attempt committed. Source scope as well as month must match before a recorded SHA can be replayed.

`already_imported` is a ledger replay decision, not a fresh validation of every previously stored row or proof that those rows were never changed. It does not repair a damaged or manually edited dataset.

Schema initialization is a separate earlier operation and can create/upgrade an empty research database even when the subsequent batch fails. This is atomicity of flight/ledger changes, not atomic creation of the complete environment. SQLite's existing connection timeout still applies: a long competing writer may cause a busy/timeout error. There is no automatic retry scheduler. A later authorized replay can inspect the ledger and avoid duplicating a completed batch; arbitrary concurrent workloads are not qualified by the small tests.

## Input limits

- Archive at most 512 MiB, copied in 1 MiB chunks to temporary storage.
- Bounded ZIP central-directory metadata: declared/actual member count at most 16, directory at most 64 KiB; one CSV with declared size at most 2,000,000,000 bytes. Multi-disk archives, oversized ZIP64 sentinel metadata and unsupported/encrypted compression profiles are refused; this is not a general ZIP compatibility guarantee.
- Stored/deflated ZIP members only; CSV is streamed without extraction to supplied paths.
- At most 5,000,000 CSV records and 1,048,576 characters per physical text line, with Python CSV's additional field constraints. Missing/extra record fields and duplicate header names are refused.
- A cooperative 120-second budget across capture, row/line processing and SQLite progress callbacks. It is not a hard I/O deadline or a representative-volume throughput result. A private archive copy requires temporary disk capacity up to the archive cap.

Existing selected-field normalization and default BTS source labels remain unchanged for approved external inputs. This does not verify every business invariant, published airline schedule, source right or real-world accuracy. Archive/source URL labels alone do not authenticate an origin or authorize an import. Existing intake receipts still do **not** grant import approval automatically; no intake authorization policy is changed here.

## Synthetic scope

Generated research fixtures use `synthetic=True` in the library or `--synthetic` in the existing privileged import CLI. Their flight `source` is `SYNTHETIC_BTS_SCHEMA` and their ledger URL is `urn:ain:synthetic-bts-schema:<period>`. They are excluded from queries limited to `BTS_REPORTING_CARRIER`. The same archive hash already recorded under one scope cannot be relabelled as the other scope through replay. The flag must be an explicit boolean; it is not an authenticity attestation for arbitrary input files.

The real importer retains its existing database argument/default for compatibility. It is an OS-owner data tool, not a new API permission path. Do not point generated fixtures or unapproved data at the primary database.

## Safe repeatable drill

```powershell
.\.venv\Scripts\python.exe -m pipelines.verify_import_safety
```

This host-only command accepts no existing archive/database argument. Each invocation creates an exclusive case under `.local/import-safety/<random-id>/`, generates its own clearly synthetic CSV/ZIP and writes only new research databases. It reconciles four input records into three stored identities and one identical duplicate, replays the batch, rejects a source-scope relabel, verifies conflict/invalid-row rollback, executes three concurrent replays and injects a pathname change after capture to verify the consumed private copy remains bound to its hash.

The report traces one generated record ID to the isolated case's import ledger and retained archive hash. This is not a new general per-row provenance model and does not retroactively supply original import receipts for the historical application dataset. It does not process the primary database, train a model, start a service or authorize airline operations.

The drill retains ZIPs, SQLite states and a fixed stage/error report after failure, without printing raw exceptions or personal paths. Source hashes and Git revision/dirty state are recorded when available; observed source changes during a run prevent success. Existing cases are never overwritten or automatically removed. Fault injection uses only the drill's own input path; no external archive is selected. Fixture airports/carriers/dates are illustrations, not observations or confirmation of a flight.

Focused checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_import_safety.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_import_drill.py -v
npm.cmd test
```

Production still needs governed source approval, representative throughput/storage measurements, orchestrated incremental scheduling/retries, operational ownership, final-image qualification and acceptance. Time-safe joins, richer semantic quality checks and broader data-science objectives remain later work. The existing frozen models, original data and historical evidence are preserved.
