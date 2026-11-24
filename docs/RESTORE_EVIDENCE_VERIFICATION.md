# Read-only restore evidence consistency

Local foundation increment, 24 November 2026. This command rechecks a fresh schema-8 restore against its backup, unsigned receipt and audit event. It never restores data, repairs state, revokes sessions, runs a model, starts services or changes readiness policy.

```powershell
.\.venv\Scripts\python.exe -m infra.verify_restore_evidence --backup "C:\path\to\offline-backup" --restored "C:\path\to\fresh-offline-restore" --offline-copy
```

The paths are placeholders. Do not use the running dashboard's database. Both directories must be authorized, standalone offline copies, with no writers for the entire check and no SQLite WAL/SHM/journal siblings. The acknowledgement is an operator statement, not something the command can prove by examining open handles. Immutable read-only SQLite disables locking/change detection; never use this on changing files. See the existing [offline snapshot boundary](FOUNDATION_BOUNDARIES.md#implemented-offline-inspection).

## What is checked

- Strict bounded UTF-8 JSON, duplicate-key rejection, supported audited-receipt fields, exact integer/boolean types, UUID/scope/count bindings and the permitted row-count changes.
- Backup file inventory and bytes against the manifest. The model/report pair must be complete; model report and index-envelope hashes are checked without deserializing a model or running RAG.
- Both databases' integrity, contiguous schema-8 history, selected table/column/primary-key structures and the current [audit DDL/connection safeguards](AUDIT_CONTRACT_GUARD.md).
- Actual backup row counts against its manifest; the receipt's flight and revoked-session counts against the databases; an empty restored session table.
- Exact retained rows in the known core tables, ordered by their primary keys and compared in 256-row batches. Account/password-hash values are compared internally but never printed or converted into public account-row fingerprints.
- Exact historical audit rows plus exactly one new aggregate `sign_out` / `success` event with the receipt's event UUID and empty actor/subject/request fields. This checks the local snapshot/receipt/event link, not the identity of an independent recovery operator.
- Restored known artifact inventory and bytes against the backup, and observed file metadata/hashes before and after the check. Unfinished-restore markers, redirects and SQLite sidecars are refused.

Success exits 0 with `consistency_verified: true`; refusal exits 2 with fixed error codes. Reports include file hashes, snapshot/event UUIDs and limited counts, without raw account rows, passwords, tokens, usernames, personal paths, exception text or SQL contents. `receipt_authenticated`, `backup_origin_authenticated`, `historical_audit_authenticated` and `production_ready` remain false. A copied or edited set of mutually consistent owner-controlled files can still pass: this is not a signature, source authentication, historical audit attestation or independent recovery qualification.

## Deliberate scope limits

The restored copy must be **fresh, before application activity resumes**. A legitimate subsequent sign-in creates sessions/events and is outside the exact post-restore state expected here. Do not erase later application history or revoke real sessions merely to obtain a passing diagnostic. This command is not called automatically against the live dashboard and does not invalidate its ordinary restore-status projection.

Backups with queued/running or unsupported agent states are refused. Supported quiescent states are `awaiting_review`, `reviewed`, `needs_changes`, `failed`, `cancelled` and `interrupted`. Real restoration still supports the existing agent interruption/cancellation behavior; this verifier does not yet validate those intentional JSON transformations. A scope refusal does not prove that such a restore was performed incorrectly.

Each database/model file is limited to 2 GiB; manifests/receipts/reports and index JSON have smaller explicit limits. The 120-second budget is cooperative across hash chunks, row batches and SQLite progress callbacks, not an operating-system I/O deadline. Batching limits row count in memory, not the byte size of arbitrarily large individual values. Representative-volume performance and capacity are not qualified by the small synthetic tests.

The tool compares known core data and selected structures, not every extension table, SQL constraint, filesystem permission, business invariant, time claim, aviation source right, model prediction or answer quality. It does not authenticate input origin or protect against a filesystem/code owner or adversarial change-and-revert races. File reads may update access timestamps. No files or SQLite sidecars are deliberately written by the verifier.

## Repeatable synthetic example

```powershell
.\.venv\Scripts\python.exe -m infra.verify_schema8
```

The existing rehearsal now prepares a separate `offline-evidence/backup` and `offline-evidence/restored` pair inside its exclusive synthetic case, before testing restored-account sign-in. All fixture writers are closed and the rehearsal owns those inputs. It invokes the read-only verifier and saves `offline-evidence/verification.json`; the additional consistency check is required for the rehearsal to pass.

That fixture-specific copy step is **not a general recipe for copying a live WAL database**. It uses only the rehearsal's generated rows and nonexecuted model/index placeholders. It never copies the primary deployment. Do not apply it to a running or externally written database, and do not remove live WAL files to make an input appear offline.

Focused checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_restore_evidence.py -v
npm.cmd test
```

Synthetic tests cover byte/directory preservation, receipt and artifact edits, same-count row changes, changed historical events, missing offline acknowledgement, markers/sidecars/redirects, unsupported active-agent scope, duplicate JSON, resource limits, concurrent input changes and actual CLI exit behavior. Production still requires final-image and representative-data qualification, approved recovery objectives, protected/off-site evidence, HTTPS, managed identity and responsible acceptance.
