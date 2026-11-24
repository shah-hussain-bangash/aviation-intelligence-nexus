# Audited session revocation and unfinished restore interlock

Local foundation increment, 24 November 2026. Schema remains 8, with no new migration. Restore still targets an exclusive new private directory and never selects or overwrites the primary deployment. This change adds a security-event binding and normal-startup interlock, not an atomic deployment switch or independent recovery qualification.

## One transaction for revocation and its event

The restored copy's session rows are deleted under `BEGIN IMMEDIATE`. A single aggregate `sign_out` / `success` event is appended in the same transaction, using the existing event type and audit schema. If the append fails or cannot return a valid event UUID, the session deletion rolls back. The original source and backup are unchanged.

The event has no authenticated actor, subject or HTTP request ID: recovery is an OS-owner operation, not a signed-in user's logout. Do not infer that a particular user clicked Sign out. The local recovery receipt links `session_revocation_event_id` to its existing snapshot UUID and declares `session_revocation_scope: all_restored_sessions`. `revoked_session_rows` records the actual number deleted, including expired rows. A restore with zero session rows still records completion of the idempotent sign-out requirement, with a zero count.

Historical audit rows are retained exactly; the restore appends one new event rather than rewriting history or inventing earlier events. Final verification requires that event to exist with the expected action/outcome and empty actor/subject/request fields. `expected_row_changes` declares the permitted count differences: session rows decrease by the number deleted and audit rows increase by one. The existing `row_counts_preserved` flag means all other counts match under those explicit changes, not that every table count is literally identical.

The event records session revocation only. It does **not** claim the entire restore succeeded. A later agent-recovery or receipt/finalization failure can retain that committed event while the restore remains unusable.

## Unfinished restore state

Immediately after creating the new destination directory, restore writes `restore-in-progress.json` containing a snapshot UUID and start time. It removes that marker only after artifact checks, transactional revocation/auditing, agent recovery, count/event verification and successful receipt writing. The receipt file is created exclusively.

Normal API/account-management initialization refuses a marker before opening or migrating the database or starting recovery/worker hooks. Backup and backup verification also refuse marked state. The restore-status projection cannot report a successful recorded restore while a marker exists, even if a receipt was written before final marker removal failed. Marker contents need not be valid JSON; presence is sufficient. An unreadable marker observation fails closed.

Failures retain their private destination and marker for investigation:

- Before revocation commits, copied session rows may remain active in the **failed copy**. The marker prevents normal application startup; no successful receipt is issued.
- After revocation commits, the sessions stay revoked and the aggregate event remains, but a later failure still leaves the marker and no usable success state.
- If receipt writing completes but marker removal fails, the receipt is not sufficient: startup and the recorded-status projection still refuse the marked directory.

Retry into a new directory after investigating the dependency. There is no automatic marker clearing, repair, retry into the failed target, rollback of the entire multi-step restore or deletion of failed evidence. Never manually clear a marker simply to make a failed copy start.

This is an application startup interlock, not filesystem access control or a global lock. A privileged operator, raw SQLite library caller or other software can bypass it. Restore starts no service; operators must not point a service at a new directory until the function has succeeded. The small interval between directory creation and first marker write is not a coordinated publication boundary. Power-loss durability, atomic directory publication and concurrent-operator coordination are not qualified by these tests.

## Inspection and verification

The CLI returns the receipt with snapshot UUID, event UUID, aggregate scope and count. The event can be inspected in the restored SQLite audit table or the existing admin-only bounded audit endpoint after signing in with the existing account credentials. The general platform receipt projection retains its previous sanitized fields; it does not expose new event details to every role. Receipts and events remain local and owner-editable, without independent authentication or protected external storage.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_audited_restore.py -v
.\.venv\Scripts\python.exe -m infra.verify_schema8
npm.cmd test
```

Synthetic tests verify success/event binding, zero-session behavior, rollback on failed/unbound audit writes, failure after the revocation commit, failure after receipt writing, preserved source sessions, startup refusal before connection, marked snapshot/backup refusal and unchanged historical events. The existing synthetic schema-8 rehearsal now checks retained audit rows **plus** the one receipt-bound restore event. Its placeholder artifacts are never used for inference.

The persisted marker protocol is included in selected state-contract fingerprints. Existing build-bound receipts remain historical; final merged-source images and a representative isolated restore still need qualification before any real deployment. These changes do not establish HTTPS, managed identity, trusted audit attribution, off-site encrypted recovery, real model parity, approved RTO/RPO or production readiness.
