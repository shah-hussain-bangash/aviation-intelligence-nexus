# Synthetic schema-8 upgrade and recovery rehearsal

Local foundation increment, 24 November 2026. A repeatable host-only command now tests the database transition and two distinct recovery points. It does not operate the primary deployment, run a Docker image or authorize a rollout.

```powershell
.\.venv\Scripts\python.exe -m infra.verify_schema8
```

Each invocation creates an exclusive new case under `.local/schema8-rehearsals/<random-id>/` and writes `report.json`. It accepts no live database, existing volume or container-project argument. Existing cases are never overwritten or automatically deleted. Container mode, enabled jobs/monitor/mount flags, redirected paths and unsupported configuration are refused. The library function accepts a fresh destination for isolated tests; that function is not a general live-state admission gate.

The command pins the canonical LF-normalized SHA-256 of `infra/fixtures/schema7.sql`: `19a82f18d759702069cdff7ad07689a137eccb558c39ee684fa7e5dd171f2eef`. Its DDL was extracted from the schema-7 initializer in [revision 515cb8c](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/515cb8c8121aa8a41e09f5e4d05e62280554b955/services/api/main.py). The fixture is empty schema, not a customer database or an authenticated airline source. Synthetic records and random temporary credentials are created only inside the new case. Model/index files are nonexecuted placeholders, clearly labelled synthetic.

## Executed checks

1. Create schema 7, a synthetic admin/session, one synthetic flight and one synthetic history record. Capture exact existing row values and a consistent SQLite pre-upgrade snapshot.
2. Run the real current initializer to upgrade to schema 8. Verify existing account/password-hash/session/data/history rows remain identical, the previous session still works, and no historical audit events are invented. A new sign-in must create a correlated audit event.
3. Run the schema-8 backup/verify/restore functions into new directories. Compare exact retained rows and historical audit events, require restored sessions to be revoked and the single new aggregate sign-out event to match the receipt, verify the credentials still work, and compare placeholder artifact hashes. Verify the upgraded source was not changed by the restore. See [audited restore behavior](AUDITED_RESTORE.md) for failure interlocks and event semantics.
4. Copy the unchanged pre-upgrade snapshot to a separate schema-7 return-point directory and revoke its restored sessions. Verify its schema, integrity and pre-upgrade row values. Confirm the schema-7 admission guard rejects the upgraded schema-8 database.
5. Exercise the rollback metadata guard using explicitly synthetic release records. An 8-to-7 pair must be rejected. No real image identity or compatibility is inferred from these synthetic records.
6. Record source file hashes, Git revision/dirty state when available, fixture identity and check outcomes. Changed source hashes during a run prevent a passing report. Failures retain their case and a fixed stage/error report, without raw exceptions or account values. Git identity may be unavailable in source bundles; file hashes are still recorded.

The later [restore evidence verifier](RESTORE_EVIDENCE_VERIFICATION.md) is also required to pass on separately prepared offline copies of this command's own quiescent synthetic backup/restore pair. Its JSON report is retained under `offline-evidence/verification.json`. The copies are made before restored-account sign-in; they are not live application data and do not provide independent source authentication.

The report excludes passwords, hashes of account rows, session values and absolute local paths. The **private case files contain generated synthetic credentials/session state and plaintext backups**; keep them out of Git. A failed fixture hash or environment admission is rejected before case files are created. A later failure may leave a partial private case for investigation. Cooperative limits in existing backup/read routines are not a hard deadline for the whole rehearsal.

## Runtime safeguards changed

Backup verification now requires contiguous supported migration history, rather than trusting `MAX(version)`. A gap with maximum version 8 cannot qualify as a verified backup. The existing `ValueError` refusal boundary is retained for recovery callers.

Rollback drills reject schema/contract-incompatible metadata before Docker inspection, state probing or switching. A matching metadata pair is only a necessary preliminary check; pinned-image inspection, actual state/job observations and the existing isolated drill remain required. Nonpositive schema versions and boolean/negative/missing job observations cannot qualify. The `prepare` action still only writes an override; it is not a compatibility certificate or authorization to run it.

## Limits and release dependencies

The schema-7 return point is **pre-upgrade state**. It contains none of the schema-8 audit events or other post-upgrade writes. Restoring it would lose those later changes; acceptable data loss and reconciliation require an explicit deployment decision. This rehearsal never overwrites the upgraded database or the primary deployment and never attempts an in-place downgrade.

No old/new image is built, inspected, started or switched. No actual schema-7 API is exercised. There is no measured prediction/RAG semantic parity, full-volume/performance qualification, production recovery-time/recovery-point acceptance, encrypted/off-site backup proof or independently protected recovery. This fixture also does not exercise interrupted agent jobs; existing focused recovery tests cover their local interruption behavior separately.

The revised recovery source changes selected state-contract fingerprints again. Earlier build-bound rollback receipts remain historical. Before a real rollout, verify final merged-source CI, bind actual immutable images, obtain an existing-release backup, rehearse against an authorized representative copy in isolation, exercise application journeys and model/index parity, qualify the restore/return procedure and obtain the release decision. Production readiness and all independently unaccepted requirements remain open.

Focused tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_schema8_rehearsal.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_releases.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_recovery.py -v
npm.cmd test
```
