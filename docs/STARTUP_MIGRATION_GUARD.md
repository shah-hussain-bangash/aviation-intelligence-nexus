# Startup migration-history guard

Local foundation increment, 24 November 2026. Adds runtime history admission; its initial implementation used schema 7 without a new migration. The following [security-audit increment](LOCAL_SECURITY_AUDIT.md) advances the source to schema 8. This is not managed database availability or production acceptance.

Previously initialization used the highest recorded version alone. A history containing 1, 2, 3, 5, 6, 7 could therefore appear current. `services/api/migrations.py` now requires integer versions forming a contiguous prefix from 1, with no version newer than the running service. The history table must be a table with an integer version primary key and an `applied_at` column. Checks emit fixed diagnostic codes, without paths or row values.

Initialization checks history before changing journal mode, then repeats the check after `BEGIN IMMEDIATE` obtains the migration write lock. Only an empty database without other user schema objects may bootstrap. Existing state with missing or empty history is refused instead of adopted. Supported contiguous older histories still run the existing transactional migrations; the final history is checked before commit. Initialization failure occurs before job recovery, worker startup and monitor startup.

An invalid history detected by the first check never reaches migration DDL or the journal-mode change. If a concurrent change is detected by the second check, the transaction is rolled back; connection opening or journal-mode handling may already have affected SQLite sidecars/metadata. This live routine is not the byte-preserving offline inspector. Do not run it against arbitrary snapshots as a diagnostic command: it can initialize or upgrade valid older databases.

`/health/ready`, authenticated `/api/v1/status`, the database monitoring probe and the authenticated platform-status projection also require the current contiguous history. A history gap discovered after startup yields readiness/status 503 and `database_ready: false`; liveness remains available. The error response does not expose the history contents. These are sampled checks, not authorization or a per-request database fence: they do not stop all other routes/workers if an owner edits history during runtime. Stop and investigate a failing deployment; never manually insert missing versions to claim a migration ran. Synthetic test repairs only restore deliberately deleted fixture metadata.

This validates migration **history**, not the entire schema or whether each migration was truthfully applied. A contiguous history can coexist with missing columns, indexes or semantically invalid data. The separate [offline inspector](FOUNDATION_BOUNDARIES.md#implemented-offline-inspection) checks additional selected structures. Neither check authenticates data provenance, supplies protected audit, validates all additional store tables, or replaces migration/recovery review. Database permission, timeout, journal-mode and migration execution failures can still prevent startup.

Focused checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_startup_migrations.py -v
npm.cmd test
```

Disposable synthetic fixtures exercise initialization, concurrent restarts, preserved records, rejection before writes, missing/empty/invalid/view histories, the second check under the write lock, transactional upgrade failure, blocked lifespan hooks and health/status failure/recovery. Existing legacy-upgrade tests continue to cover successful version-two migration with retained flights. No real account or dataset is needed. No primary deployment is rebuilt by this source change.
