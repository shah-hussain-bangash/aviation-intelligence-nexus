# Restored historical prediction API journey

The restored-data rehearsal has an optional prediction mode. Its default mode still performs authenticated data reads without deserializing a model or creating research runs.

```powershell
.\.venv\Scripts\python.exe -m infra.restored_data_api --recovery-report "<qualified private full-snapshot case>/report.json" --report-sha256 "<64-character report SHA-256>" --expected-recovery-revision "<40-character recovery verifier revision>" --with-prediction --trusted-local-model
```

Both flags are required to execute prediction mode. Joblib is executable serialization: the trust flag is an explicit OS-owner decision about the already pinned, reviewed local artifact. It is not a safe upload mechanism or confinement boundary for untrusted models. The qualified report and selected state contracts must pass the existing admission checks; a complete unchanged model/report pair is required before any service starts.

## Additional journey

1. On another private restored-state copy, obtain a direct expected result from the unchanged `ResearchPredictor` for AA/JFK/LAX, May 15, 2025 at 09:00. No model fitting or selection occurs.
2. Sign in normally through the gateway using the disposable researcher account. Submit that historical schedule with a fresh UUID request key. The response must match the direct copied-artifact result, retain its exact artifact hash and research-only warnings, and deny operational serving approval.
3. Repeat the same request/key: it must return the same saved run with `replayed=true`. Change the input under the same key: it must return a conflict without a probability. An extra outcome-label input must be rejected without a saved run.
4. Explicitly restart only the owned test API process, keeping the gateway and client cookie. After readiness, the same key must replay the same persisted result and the researcher's history must contain exactly that run. This is an explicit local restart, not automatic failover or a production recovery objective.
5. Sign in as the disposable viewer. Its history must remain empty; even a known researcher request key must not allow replaying a prediction or obtaining a probability.
6. After logout/shutdown, preserve every original account, business-history row and artifact. Permit exactly one new researcher-owned prediction row with its expected key/input/result/model/artifact/owner bindings. Original research rows are hashed separately, so adding the expected probe run does not conceal changes to old history. Migration/audit and session checks remain in effect.

The report adds `prediction`, `prediction_checks` and mode flags. The private plan contains the expected public research result/request key, but no login password, session token or CSRF token. As with the read-only mode, the two new probe accounts and six identity events are confined to the disposable copy. All owned services stop in cleanup. The selected input and main deployment remain unchanged.

## Verification and limits

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_restored_data_api tests.test_restored_prediction_api -v
npm.cmd test
```

The new tests fit a small synthetic classifier solely as a test fixture, then exercise actual gateway/API processes, persistence, restart, conflict and viewer controls. They reject missing trust/pairs and changed model bytes before service launch. Post-run negative checks detect an altered original history row and a duplicate probe prediction. Separate native execution evidence is required for the existing historical US model and retained database.

The example is a **historical research schedule**, not confirmation that a flight existed. The date belongs to the already evaluated test period; repeating inference is not a fresh independent holdout or airline accuracy evaluation. No new model is trained, no operational recommendation is issued, no original user's password is tested and no branch is deployed. Generated-answer quality, provider-weight/off-host recovery, HTTPS/managed identity and production acceptance remain open.
