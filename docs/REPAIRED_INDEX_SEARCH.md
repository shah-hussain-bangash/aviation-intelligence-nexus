# Authenticated service checks using a repaired index copy

`infra.verify_repaired_search` follows the [offline index repair](INTERRUPTED_INDEX_REPAIR.md) with a normal API/gateway search rehearsal. It copies only the repaired public-document index into new private state, creates three disposable accounts and an empty database, and exercises authenticated evidence search. It does not open the original flight/account database or start services in the original repaired case.

```powershell
.\.venv\Scripts\python.exe -m infra.verify_repaired_search --repair-report .local/index-repairs/<repair-receipt-case>/report.json --report-sha256 <full-receipt-sha256> --expected-repair-revision <full-repair-code-revision>
```

Python dependencies, Node and the existing `embeddinggemma:300m` model on fixed Ollama loopback port 11434 are required. Defaults are web port 18280 and API port 18202, both loopback-only; optional ports must be distinct, unused and unprivileged. No model download or provider installation is performed.

## Evidence admission and fresh state

The supplied receipt must be a successful private `ain-owned-index-repair-v1` report with exact byte hash, expected clean code revision and unchanged repair-tool fingerprint. Its source-case identity, original plan hash, retrieval/recovery flags, recorded index hashes, independent retained/restored files and exact current corpus chunks are rechecked. Changed receipts, files, plans or repair code require new qualification rather than silently accepting old evidence.

These are consistency checks of unsigned operator-selected evidence. They do not authenticate an earlier operator or independently prove that another case's services were stopped. Only artifact files are read from the original repaired case.

The new case lives under `.local/repaired-search/<unique-case>`. Its worker refuses an existing database and creates a fresh schema-8 database plus synthetic admin/researcher/viewer accounts. A random password is kept in memory and sent to preparation over stdin; it is not written into command arguments, plans or reports. The index is copied and pinned. No flight rows or production account rows are copied. Direct evidence-only probes establish a local baseline and verify the installed embedding digest.

## Normal HTTP journey

The regular Uvicorn API and Node gateway use the test profile and isolated `ain_test_session` cookie. No session or authentication bypass is injected.

- Check database-backed readiness, static dashboard availability and anonymous history denial.
- Log in as the synthetic researcher. Run a session-expiry evidence query and an unrelated photosynthesis query, both with `generate: false`; require parity with direct results and no generated claims.
- Restart only the owned API. Verify the same session can read the two saved runs afterward. This step verifies history persistence, not a new post-restart search request.
- Log in separately as the synthetic viewer. Require empty owner-scoped history and 403 on query mutation.
- Check CSRF enforcement and normal logout. Stop all owned service handles, including attempts to stop every handle when cleanup errors occur.

Post-shutdown SQL requires three synthetic accounts, no sessions, seven account/sign-in/sign-out audit events, exactly two researcher-bound knowledge runs with matching IDs/payloads/timestamps, and zero flight/import/prediction/gate/agent rows. Copied index bytes and all original repair inputs must remain unchanged.

## Verification and limits

Focused check: `python -m unittest tests.test_verify_repaired_search -v`. Tests inject synthetic embedding functions only into disposable worker/API processes while preserving normal HTTP authentication. They cover receipt/tool/revision pins, changed repaired bytes, invalid ports, sanitized preparation failure and the real proxy/search/restart/viewer/logout flow. Native execution against the existing local provider is separate evidence. Run `npm test` for regression checks.

The report records repair receipt/revision, index/provider identity, evidence counts, saved IDs, test-state checks and process cleanup. The flight-record count is explicitly **zero** in this synthetic database. This is repaired-index service integration, not recovery of the user's original account/database, embedding weights, a browser journey, generated-answer quality, cloud deployment or automatic application recovery. Production acceptance remains open.
