# Offline batch, archive, ledger and row reconciliation

Ninth new local data-platform increment, 24 November 2026. A successful runner state is not proof that stored flight values still match retained inputs. The new verifier reconstructs the selected synthetic dataset in a private temporary database and compares every selected row with an explicitly offline case. It never repairs the source.

```powershell
.\.venv\Scripts\python.exe -m pipelines.verify_case_reconciliation
.\.venv\Scripts\python.exe -m pipelines.reconcile_synthetic_case "<offline-synthetic-case>" --offline-copy
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_case_reconciliation.py -v
npm.cmd test
```

The demonstration creates a new case under `.local/case-reconciliation/<case_id>/`, imports two generated batches and quarantines a conflicting third batch. It verifies the original case, deliberately changes a separate copied dataset, and changes queue metadata in another copy. Both negative copies remain retained and are not repaired. Existing cases, historical application data, frozen experiments and the running deployment are not selected.

## Admission and read-only source boundary

The CLI requires `--offline-copy`; the library requires the literal `offline_copy=True`. This is the caller's declaration that the case is quiescent and offline, not a process-liveness probe or exclusive lock. The existing synthetic marker/unredirected local path checks apply. The verifier refuses queued/running work and SQLite WAL/SHM/journal sidecars. Do not use it against an active runner, even if that runner is temporarily idle.

Queue and source flight databases open with `mode=ro&immutable=1`, query-only mode and trusted-schema disabled. Source migration history must be current schema 8; an integrity check runs before comparison. The verifier deliberately writes only its own new temporary reconstruction, which is removed when its context ends. No source SQLite initialization/migration, queue mutation, lock acquisition, reset, approval or data correction is performed. Normal OS access-time bookkeeping is outside the no-deliberate-write claim.

Selected input bytes, file identity/size/modification observations and top-level/archive directory entries are checked before/after. A concurrent change can refuse the result; this does not make concurrent verification safe or authenticate a privileged filesystem owner. The comparison can only describe the observed offline bytes. It is not current health, an import authorization or cryptographically authenticated origin.

## Comparison rules

At most 100 recorded jobs are accepted, with at least one succeeded batch. Each retained job archive is rehashed and must match the queue identity, including archives retained for blocked/quarantined work. Only succeeded batches are parsed/reconstructed. Their queue result must bind to the same hash, source scope, declared month and recorded ledger counts.

Reconstruction uses the **same bounded importer and normalization implementation**, with synthetic mode and expected archive hashes, against a fresh scratch database. This checks reproducibility and stored-content consistency; it is not an independently implemented parser or proof that the original source values are true. Conflicting retained successful batches cannot produce a consistent reconstruction.

The archive set, period, source URL and read count must match the source import ledger. Each ledger must reconcile read = inserted + duplicates, queue result counters must match that ledger, and total recorded inserts must equal the stored distinct-row count. Selected flight columns are streamed in key order in blocks of 256 and compared exactly with reconstruction: source/key, date/carrier/airports, departure/arrival delays, flight number/time and cancellation/diversion flags.

Generated database IDs, import timestamps, identity/account tables, model artifacts and unselected application tables are not compared. Overlapping batches can execute out of queue order; their original per-batch insert allocation is not independently reconstructed. The verifier checks recorded allocation arithmetic and total inserts, rather than falsely assuming queue order was execution order. It does not authenticate those original accounting records.

An import present in the source ledger but absent from succeeded jobs is unresolved evidence, not silently accepted. For example, repeated post-commit crashes can leave a quarantined job whose data already committed. Such cases require review. A consistent selected dataset may still have terminal review jobs with no committed import; the report exposes their count. `consistent=true` does not clear quarantine/blocked work or make the queue operationally healthy.

## Limits and evidence

The aggregate tracked input size is capped at 2 GiB, with the same per-file ceiling and at most 4,096 characters for each successful queue result. The case's source is synthetic by contract, and rebuilt rows keep `SYNTHETIC_BTS_SCHEMA`. No external data is downloaded or approved.

A cooperative 120-second budget is checked during hashing/streamed comparison and through source SQLite callbacks. Reconstruction calls retain the importer's own bounds and deadline; they can overrun the outer budget before its next check. This is not a hard IO/CPU deadline or representative-volume measurement. Scratch disk capacity is required in addition to retained source files. Temporary cleanup only targets the verifier's newly created scratch directory, never source cases.

The report includes tracked input hashes, reconstructed row count, successful/retained job counts, ledger count, fixed error codes and terminal review count. It prints no raw flight records, private source paths or exception details. The demonstration additionally records source revision/dirty state where available and selected source hashes. Its ten checks reconcile four identities and two ledgers, preserve quarantine evidence, and verify altered rows/queue bindings are rejected without modification.

Focused tests cover changed values/archives/result counts, explicit offline admission, sidecar/size/pending-job guards, reordered overlapping batches and unacknowledged committed work. Source authentication, representative workloads, full model/application state reconciliation, independent supervision and production acceptance remain open. This verifier does not complete those requirements or establish production readiness.
