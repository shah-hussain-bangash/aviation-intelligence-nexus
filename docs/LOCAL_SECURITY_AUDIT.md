# Transactional local security events

Local foundation increment, 24 November 2026. Proposed source change only: the existing Docker deployment and account credentials are unchanged. The application schema advances from 7 to 8 to add `security_audit`. This is a local audit trail, not protected external storage or production acceptance.

## Coverage and privacy

The event records account creation, successful/denied/rate-limited sign-in, sign-out, OS-owner access changes, and revocation of other sessions. Identity mutations and their event are committed in the same SQLite transaction. If an event insert fails, the corresponding mutation rolls back. Denied and limited sign-in events commit before the normal denial is returned. Audit storage failure produces an unavailable response rather than accepting an unaudited sign-in or claiming sign-out/revocation succeeded. Existing sessions can still read permitted data; this is not a global service shutdown on audit failure.

Each event has a sequence, random event UUID, UTC timestamp, allowlisted action/outcome, optional account UUIDs and optional server request UUID. No usernames, supplied passwords, password hashes, session tokens/token hashes, IPs, raw headers, query strings, prompts or arbitrary payloads are stored. Unsuccessful sign-ins omit actor and subject identifiers, including unknown-account attempts. Noncanonical/non-v4 identifiers are omitted; account identifiers produced by the normal store are v4 UUIDs. Account UUIDs are **pseudonymous personal data**, not anonymous data; protect access and retention accordingly.

Successful sign-in identifies its actor/subject; account creation/access change identifies the subject, with no claimed signed-in actor because those operations use the local OS-owner CLI. Direct store/CLI calls have no HTTP request ID. API sign-in/sign-out/session revocation use the server-generated request ID, ignoring the caller's `X-Request-ID`. A sign-out reaching the store after another revocation may have an unknown actor. Timestamps use the local clock and are not independently attested.

This initial coverage does not include rejected Origin/CSRF requests, input validation failures, read access, every permission denial, service failures, session expiry/rehash/automatic cleanup, agent actions, restore session revocation or every business mutation. Access-change events record occurrence and subject, not a before/after role diff. There is no claim of complete forensic reconstruction.

## Access and local controls

`GET /api/v1/research/security-audit` is an admin-only, read-only API. Anonymous callers receive 401; researcher/viewer roles receive 403. It accepts no query parameters and returns the latest 100 events plus a flag indicating older events. It never returns all account names or session identifiers. There is no new dashboard screen in this increment. The existing gateway forwards only the fixed GET route and scoped session cookie; the API enforces the role. There is no API to append, edit, delete, filter by arbitrary SQL or change retention.

SQLite triggers reject ordinary UPDATE/DELETE statements on the audit table. These are accidental-edit guards. A database/filesystem owner can drop triggers, alter data, replace the file or truncate history; no cryptographic chain, independent witness, write-once storage, deletion detection or tamper-proof claim is made. An administrator role at the API is not the same authority as the OS/database owner. The application retains write access because it must append its events.

The read is query-only, fixed-size and has a cooperative query budget; SQLite may manage live WAL sidecars. This is not the offline immutable snapshot command. Events currently accumulate without automatic pruning, off-host delivery or storage quotas. Flood resistance, disk capacity, retention/legal policy, redaction approval, delivery/retry and collector failure behavior need qualification before production. Current per-username sign-in limits are not a global anti-abuse policy.

## Migration, recovery and rollback

Version 8 creates the event table and UPDATE/DELETE guards inside the existing migration transaction. A valid version-7 database upgrades without changing account IDs, password hashes, sessions, flights or existing history. It does not backfill historical events or invent earlier activity. The startup guard continues to reject gapped/future histories. The offline preflight checks the added table/columns/primary key/event-ID uniqueness; it does not validate trigger definitions or every SQL constraint.

The recovery inventory now counts audit rows; the existing consistent database snapshot includes the table. Synthetic recovery tests verify exact retained events through restore. This is not a fresh recovery qualification for the real deployment, and restore-driven session invalidation does not append a new security event yet.

**Schema compatibility changed.** The prior schema-7 image cannot start on a schema-8 database. Old rollback/build evidence is historical and is not requalified by these tests. Before any eventual deployment, take a verified version-7 backup using the existing release, rehearse upgrade/restore on isolated state, bind new images and state contracts, and review the return path and acceptable data loss. Do not deploy this branch or attempt a downgrade because a PR passes. No real database is upgraded by editing source files alone.

The later [synthetic schema-8 rehearsal](SCHEMA8_REHEARSAL.md) makes the local database exercise repeatable and verifies a separate pre-upgrade return point. It does not qualify actual images, representative data, model parity or the primary deployment.

## Verification and remaining requirements

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_security_audit.py -v
npm.cmd test
```

Synthetic fixtures exercise atomic success/failure, privacy, denied/limited attempts, concurrent sequences, role/method/query boundaries, server request correlation, unavailable audit storage, version-7 upgrade and retained sessions, local append guards, bounded output and backup/restore. All 64 workspaces and the historical/synthetic research labels are retained.

Production still requires independently controlled protected storage, approved event coverage and retention, identity attribution, trusted time, tamper/deletion detection, durable delivery and failure policy, least-privilege database roles, capacity/abuse testing and responsible acceptance. HTTPS, managed identity and production readiness remain open.
