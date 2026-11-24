# Foundation boundaries and offline schema admission

Status: proposed architecture and an implemented local inspection command, 24 November 2026. No HTTPS endpoint, external identity integration, managed database, release admission gate or cloud resource is installed by this change. The current local accounts and runtime are unchanged. Production profiles remain rejected by configuration validation.

## First private release boundary

The intended service is a private historical aviation research portal. Its first production audience, simultaneous users, request mix, latency objective, availability objective, recovery point and recovery time still need an owner-approved workload and measurements. Do not invent commitments from the current single-workstation results. Keep the existing 64 workspaces and synthetic operational labels; do not treat prototype navigation as implemented business services.

| Boundary | Proposed implementation and acceptance evidence |
| --- | --- |
| Browser to gateway | One approved HTTPS origin, managed certificate renewal and private access controls. No direct public API, database or Ollama port. Verify the actual certificate, redirects, secure session cookies, origin/CSRF checks, security headers and expired-certificate behavior before external use. |
| Gateway to API | Private routing and explicit trusted proxy addresses/hops. Discard caller identity and forwarding headers; derive identity server-side. Never enable broad proxy trust merely because TLS terminates upstream. Exercise forged headers and direct API bypass attempts. Current loopback/container routing is not evidence of cloud network isolation. |
| Identity to application | Use a maintained OpenID Connect client with authorization code flow and PKCE S256, exact registered callback, state and nonce correlation. Validate signature/allowed algorithm, issuer, audience, expiry and nonce, plus authorized party where applicable. Keep tokens server-side and issue a separate revocable application session. Test replay, wrong issuer/audience, expired tokens and unavailable key discovery. |
| Roles and ownership | Bind an external identity by issuer and subject, never an unverified email or display name. Map approved identities/groups to explicit local roles with default denial. No automatic admin grant and no implicit conversion of the existing `shah` password account. Preserve owner-scoped history. Test analyst/admin separation and cross-user object access after integration. |
| Session lifecycle | Require identity-provider MFA policy, sign-out, account disablement, session revocation and bounded lifetimes. Test each deployed behavior. Define an explicit migration and recovery process for local accounts before changing authentication; never export password hashes to an identity provider. |
| Secrets and audit | Use the selected platform's protected secret service/workload identity and least privilege. Keep tokens, credentials, prompt contents and personal data out of request logs. Correlation logs are best-effort diagnostics; protected security audit needs independent access, retention, tamper resistance and event coverage. |

These are design requirements derived from [OpenID Connect token validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation) and [OAuth security best practice, RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html), plus project-specific decisions. Provider, tenant, domain, access policy and responsible owners remain deferred. No new environment switch claims these controls exist.

## Database migration and availability boundary

Retain SQLite for the local research environment. Source now targets schema 8 through the proposed [security-audit migration](LOCAL_SECURITY_AUDIT.md); the existing schema-7 deployment is unchanged. A future shared deployment should evaluate a managed relational database (PostgreSQL is a candidate, not an implemented adapter) against measured concurrency and recovery requirements. Current stores issue SQLite-specific SQL and create additional tables outside the core migrations too; changing a connection string cannot migrate this application.

Before any engine or schema change:

1. Inventory all stores, ownership/idempotency rules, nullable legacy ownership, indexes and application-managed relations. Account/session values remain private.
2. Implement versioned migrations in an isolated target with least-privilege runtime access. Use an exclusive migration lock and explicitly tested transaction behavior. Fail startup on gaps, unknown versions or failed migration; do not infer history from its maximum alone.
3. Back up and restore into isolation. Reconcile source/import counts, account identities, ownership and unique/idempotent keys, timestamps, JSON payloads and selected model/index hashes. Revoke restored sessions. Re-run predictions and role-bound journeys.
4. Measure concurrent readers, writers and workers, lock timeouts, retry/idempotency behavior and interrupted migration recovery at a representative scale. The current offline inspection is not a concurrency test.
5. Prefer additive, backward-compatible changes and a reviewed cutover. An older application image cannot safely roll back incompatible database changes. Define rollback compatibility or a separately verified restore and acceptable data loss before deployment.

No managed engine, standalone migration runner, high availability or independent off-site recovery is implemented here. The later [startup migration-history guard](STARTUP_MIGRATION_GUARD.md) checks contiguous history during initialization and health checks. The offline command below remains a separate review aid for additional selected structures, not an automated release gate.

## Implemented offline inspection

Run from the project directory with an **existing, standalone offline snapshot**:

```powershell
.\.venv\Scripts\python.exe -m infra.schema_preflight "C:\path\to\offline-snapshot.sqlite3" --offline-snapshot
```

The path is an example, not the live project database. Do not run this on the running dashboard's state. Use a previously verified stopped/checkpointed snapshot or a disposable synthetic fixture. Do not copy the main file of a live WAL database without a consistent backup procedure. This command never creates a snapshot, authenticates its provenance, or authorizes a restore/import.

The acknowledgement means the operator has ensured no writers can access the snapshot for the entire inspection. It cannot discover all open handles or prove that condition. SQLite's [immutable option](https://www.sqlite.org/uri.html) disables change detection and locking and is unsafe for changing database files. Accordingly the command rejects WAL/SHM/journal siblings, redirected paths, missing/nonregular files and files outside its 2 GiB size allowance before connecting. It uses `mode=ro&immutable=1`, query-only mode and disabled trusted schema. SHA-256 and file metadata are compared before/after successful checks. These observations do not eliminate races or protect against a malicious filesystem owner. Keep untrusted files outside this workflow.

Checks: SQLite integrity, contiguous migration records 1 through 8, required core tables/column names, primary-key columns, the documented owner/history indexes, and selected uniqueness constraints. It does **not** fully compare SQL types, nullability, defaults, collations, triggers, all additional store tables, row semantics or access rights. It does not read/export account values, calculate dataset row counts, load artifacts, import the API, invoke migration code or open the default live database. Reports omit local paths, raw exception messages and row contents.

The later [audit-specific contract check](AUDIT_CONTRACT_GUARD.md) adds expected table/trigger DDL and current-connection safeguard checks for `security_audit`. The general limitations above still apply to the remaining schema and data; this is not full database or historical-log authentication.

Successful inspection exits 0 with `local_schema_checks_passed: true`; refusal exits 2. Older contiguous histories report `migration_required`; gaps, newer versions and structure failures remain blocked. All reports retain `production_ready: false`. The 30-second budget is cooperative (hash chunks and SQLite progress callbacks), not a hard operating-system I/O deadline. No migration or production approval follows from a pass.

Focused verification:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_schema_preflight -v
npm.cmd test
```

Tests create disposable synthetic accounts and databases. They verify byte/directory preservation, safe CLI output, consent/sidecar refusal, old/new/gapped histories, missing structures, corrupt/oversized files, observed changes and cooperative budget exhaustion. They do not claim the primary deployed database was inspected. No UI change or deployment is needed for this increment.
