# Full retained snapshot recovery in private copies

`infra.full_snapshot_recovery` checks a complete, manifest-pinned offline backup using new native directories. Unlike synthetic-only drills, the selected backup may contain real retained historical flight records and account/history rows. All copies remain private. It never selects the running deployment, starts an API/dashboard, changes the input backup or deploys a release.

```powershell
.\.venv\Scripts\python.exe -m infra.full_snapshot_recovery --snapshot "<reviewed offline backup directory>" --manifest-sha256 "<64-character manifest SHA-256>" --offline-snapshot
```

The acknowledgement means the OS owner has selected a quiescent retained backup, not an active application state directory. The digest identifies chosen bytes; it does not authenticate the publisher. No SQLite backup should be inferred to be current just because this command passes.

## Admission and resource budget

The pinned manifest must contain a valid snapshot UUID, schema 7/8 metadata, a complete version-appropriate count inventory and unique allowlisted file entries. The SQLite database is mandatory; any model artifact/report must form a pair. All files must be bounded ordinary local files with exact size/hash matches. Symlinks/junctions, remote paths, SQLite `-wal`, `-shm` or `-journal` sidecars (including empty ones), changed bytes and unexpected inventory entries are refused.

Admission requires free disk space of at least six times the selected file bytes plus 1 GiB. This is a conservative local headroom check, not a reserved quota. The drill retains an input-state copy, new schema-8 backup, restored state and two offline evidence copies. Large inputs can therefore consume several times their original size. The SQLite file limit is 2 GiB; the worker has a time budget. Partial/failed cases remain private for review and are never reused automatically.

## Verification sequence

1. Copy every admitted file into a fresh case and verify all copy hashes. Do not open the source database for migration. A new child process binds its state paths exclusively to the owned copy, with workers/monitor disabled.
2. Inspect copy integrity and contiguous migration history. Stream every base table in primary-key order into row counts and SHA-256 fingerprints; do not include any row values in the report. Recorded manifest counts must match. Refuse active/invalid agent states, because this scope requires retained agent rows to remain unchanged.
3. Run the supported initializer only against the copy. Schema 7 may upgrade to 8. Existing base rows and migration-history rows must remain exact; schema-7 copies must not receive fabricated historical security events. Existing schema-8 audit rows must remain exact.
4. Back up the upgraded state and restore into a new private directory. Stream and compare retained table fingerprints, including accounts, imports and research/gate/knowledge/agent histories. The only permitted session/audit changes are all restored sessions being revoked and one bound revocation event.
5. Check all copied model/report/index artifact bytes, and run the independent offline receipt verifier on quiescent ordinary copies. It checks retained rows directly, historical audit rows and the receipt/event binding. Verify that restoring did not alter the upgraded source copy and that the original input's pinned files remain unchanged.

The worker checkpoints only its private copies, never the selected input. Model joblib files are copied and hashed without deserialization; no model trust flag, fitting or inference is involved here. The index is copied without embedding or generation calls.

## Evidence and limits

Reports are `.local/full-snapshot-recovery/<case>/report.json` and contain verifier revision/hash, source manifest/database pins, counts and aggregate table/artifact fingerprints, migration versions and restore/offline receipts. Raw rows, usernames, password hashes, session tokens, account passwords and worker stderr are not printed or published. Copied databases still contain sensitive account/history data and must remain outside Git. The original snapshot remains unmodified; the main deployment is not accessed.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_full_snapshot_recovery -v
npm.cmd test
```

Tests use small synthetic schema-7 fixtures. They cover offline acknowledgement, file/manifest pins, sidecar/count/schema admission, disk refusal, generic worker failure, full row/artifact preservation through an actual child-process upgrade/restore, and active-agent refusal. Separate native execution evidence is required for the retained historical snapshot.

This is same-host native data/migration recovery evidence. Preserved account hashes do not prove an actual password login or managed identity. The tool does not qualify live-user browser access, model prediction/retrieval behavior, encrypted/off-site recovery, independent key custody, host reboot, production RTO/RPO, workload capacity or a rollout/rollback strategy. The schema-7 input remains a pre-upgrade return point and does not contain later schema-8 events. Production acceptance remains open.
