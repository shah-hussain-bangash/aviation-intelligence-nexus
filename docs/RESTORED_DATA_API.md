# Restored retained-data API rehearsal

`infra.restored_data_api` connects a verified full restore to the normal native API and gateway on a **new private copy**. It uses disposable researcher/viewer credentials and the native-test cookie namespace. It does not start the main deployment or use an existing account password.

```powershell
.\.venv\Scripts\python.exe -m infra.restored_data_api --recovery-report "<qualified private full-snapshot case>/report.json" --report-sha256 "<64-character report SHA-256>" --expected-recovery-revision "<40-character recovery verifier revision>"
```

Python dependencies and Node 24 are required. Defaults are loopback web port `18180` and API port `18102`; optional `--web-port`/`--api-port` must be distinct, unused and unprivileged. Neither server binds a public host interface. The existing dashboard's ports and session cookies are unchanged.

## Source admission

Select a successful `ain-full-snapshot-recovery-v1` report from `.local/full-snapshot-recovery/<32-hex-case>/report.json`. The caller pins its exact bytes and expected verifier revision. Admission checks its clean-toolkit metadata, unchanged full-snapshot verifier, selected state contracts, schema 8, successful offline evidence and restore audit-event binding. Source files must match the recorded restored-database and artifact hashes; SQLite sidecars and redirected/remote paths are refused.

These are consistency checks of unsigned operator-selected evidence, not authentication of the original run or publisher. Reports themselves are not a protected release gate. A changed verifier/contract requires fresh qualification rather than silently accepting old evidence.

## Actual HTTP flow

1. Copy the admitted restored files to `.local/restored-api/<case>/state`. Verify copy hashes and available disk space. Workers/monitor are disabled; state paths are injected only into child processes.
2. Generate a random password in memory and two random probe usernames. Create researcher/viewer accounts only in that copy. Plaintext passwords travel over stdin/local requests; they are never written to the plan, report or command arguments. Original account rows/password hashes are not changed.
3. Launch the ordinary Uvicorn app and Node gateway with `AIN_ENV=test`, loopback binding and `ain_test_session`. On Windows both are hidden child processes. Their logs stay private. No bypass session is injected.
4. Verify database-backed readiness, static dashboard/security headers and anonymous denial. Log in through the proxy as each probe. Compare retained BTS totals/date bounds/carrier counts and monthly counts with independent SQL measurements of the copied database.
5. Confirm original owners' research history is hidden from the new accounts, the admin audit endpoint is denied, viewer prediction mutation is denied, origin/CSRF checks work and normal logout closes both sessions. Model inference is never requested.
6. Stop only the process handles created by this invocation. Checkpoint only the owned copy after shutdown. Stream business-table fingerprints, preserve original account rows and the historic audit prefix/migrations, and verify exactly the two new probe accounts plus six account/sign-in/sign-out events. No probe sessions may remain. Transient rate-limit housekeeping is not claimed to be unchanged. Artifact bytes and original qualified source pins must still match.

The report records HTTP checks, retained aggregate/monthly counts, state-preservation checks, verifier/harness identity and cleanup. Owned-service stop failure fails the rehearsal. Partial copies/logs remain private for inspection. No global process killing, Docker operation, scheduler or service installation is performed.

## Tests and limits

The separate [opt-in historical prediction journey](RESTORED_PREDICTION_API.md) adds explicit trusted-model admission, one persisted researcher-owned result, replay/conflict checks and an owned API restart. It is disabled by default and separately reports expected history changes; the read-only mode above remains unchanged.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_restored_data_api -v
npm.cmd test
```

Tests use small synthetic schema-7 fixtures qualified through the full-restore worker, including a source-coded BTS fixture row to verify filtering independently from a synthetic-source row. A real gateway/API test exercises HTTP login, permission/read checks, row preservation and cleanup. Tests also reject changed report/revision/contracts/database bytes, invalid scope/ports and unsafe cleanup behavior. Python CI now explicitly installs Node 24 for this integration test.

This does not test an original user's password, a managed identity, an interactive browser journey, model inference, RAG/generation, provider-weight recovery, cloud networking, HTTPS, off-host recovery or production workload. The source snapshot may predate later live changes. Successful local HTTP access to its copy does not authorize deploying the branch or establish production readiness. All operational scenario labels and original research limitations remain intact.
