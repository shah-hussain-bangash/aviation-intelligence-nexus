# Local audit schema and connection guard

Local foundation increment, 24 November 2026. Schema version remains 8. No new migration or repair is introduced, and the existing Docker deployment is unchanged. This verifies expected local safeguards; it does not authenticate historical event contents or provide independently protected audit storage.

Previously an audit insert could succeed after an append-only trigger was removed or replaced by a no-op. `require_audit_contract` now reads the application-owned audit table and trigger definitions from `sqlite_schema` and compares them to the migration's expected DDL. Missing/altered objects and additional triggers attached to the audit table are rejected. The check also rejects a connection with ignored CHECK constraints, writable-schema mode or disabled trigger execution. Python/SQLite support for observing the trigger setting is required; unsupported observation fails closed.

Only whitespace variation in the expected SQL is tolerated. This is a deliberately strict check of application-owned DDL, not a general SQL-equivalence parser. Legitimate schema changes need a reviewed migration/contract update; an operator should not relax the guard or rewrite migration history to silence a failure. Additional indexes and unrelated application objects are outside this audit-specific check.

## Where it is enforced

- Existing schema-8 startup checks before journal-mode handling, and again inside the migration transaction before commit. Fresh/older supported databases first run the existing migrations, then must pass the check before commit. Job recovery, worker and monitor startup still occur only after initialization succeeds.
- Each covered security-event append, on the same SQLite connection and inside the identity action's write transaction. A removed safeguard therefore rolls back sign-in/session creation, sign-out, account creation/access change and other-session revocation instead of committing the covered action without the expected local safeguards. Denied/limited sign-in auditing also fails closed if its event cannot be accepted.
- Readiness, authenticated status/platform projections and the monitor's database probe. Runtime drift yields not-ready/503 observations while liveness remains available.
- Admin-only audit reads, backup verification and the separate explicit offline snapshot inspector. They cannot return a healthy/verified result merely because the table exists and migration history ends at 8.

Audit errors use fixed diagnostic codes. Existing API handlers return generic unavailable responses and retain server request correlation; raw SQL, passwords, session tokens and personal paths are not returned. The admin-only role boundary is unchanged. Contract checks never create missing objects, re-enable connection settings or repair the database.

## Boundaries and failure policy

The transaction check observes the **current connection** and the audit-specific schema. It does not prove other applications' settings, validate all database tables, detect edited/deleted/reordered historical event contents, independently attest the clock, inspect filesystem permissions or resist a database/filesystem/code owner. Such an owner can bypass this application, alter the checker or replace the database. These are safeguards against unexpected local configuration/schema drift, not tamper-proof logging.

Existing sessions may still use other permitted read routes during an audit failure. These changes are not a global request fence or an automatic worker shutdown. Stop and investigate an unhealthy deployment under an approved incident procedure. Examples of manual trigger restoration in tests repair only deliberately damaged synthetic fixtures; they are not automatic production repair instructions.

The checker is read-only in SQL and is not cached between identity actions. SQLite may manage live WAL sidecars while opening a connection. The offline inspector still requires a genuinely stopped/checkpointed snapshot and rejects sidecars; a live read is not proof that a file is suitable for immutable inspection.

Moving the unchanged logical version-8 DDL into shared constants avoids drift between creation and verification. Valid existing version-8 tables/triggers are accepted with whitespace differences; account/session/data rows are not changed by the checker. Source changes alter selected state-contract fingerprints, so previous rollback receipts remain historical and require new final-image qualification.

Focused verification:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_audit_contract.py -v
npm.cmd test
```

Synthetic tests cover valid read-only checks, whitespace compatibility, missing/no-op/extra triggers, changed table constraints, disabled connection safeguards, identity rollback, startup refusal before journal changes or hooks, runtime 503/liveness behavior, backup/offline refusal and no automatic repair. Local integration evidence does not complete HTTPS, managed identity, protected external audit storage, retention/delivery policy or production acceptance.
