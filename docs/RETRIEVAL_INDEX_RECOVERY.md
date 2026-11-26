# Isolated retrieval-index outage and recovery

`infra.restored_data_api --with-retrieval --with-retrieval-recovery` extends the restored retrieval rehearsal with an actual missing-index interval in its own private copy. It never stops the shared Ollama provider or changes the running dashboard/index. The existing default, prediction and evidence-only modes remain separately selectable.

```powershell
.\.venv\Scripts\python.exe -m infra.restored_data_api --recovery-report "<qualified full-restore case>/report.json" --report-sha256 <full-report-sha256> --expected-recovery-revision <full-verifier-revision> --with-retrieval --with-retrieval-recovery
```

See [Restored Retrieval API](RESTORED_RETRIEVAL_API.md) for source admission, local embedding requirements and disposable-account isolation. The recovery flag requires retrieval mode; it does not enable generation or flight-model prediction.

## Actual fault and observations

After the normal two queries and owned API restart, the runner verifies the copied index's hash and unredirected, case-owned paths. It moves only that index to `retained-knowledge-index.json` inside the same private case. No bytes are deleted.

While the index is missing, an authenticated query must return the exact sanitized `503 knowledge_unavailable` response, with no saved run, evidence or answer. The owner's history must remain exactly the two earlier runs, and the static dashboard must still return 200. This dashboard liveness check is not a backend-readiness assertion.

The runner restores the retained original bytes, refuses to overwrite any unexpectedly created index, and checks the original hash again. Another authenticated evidence-only query must match the original direct result, have a new run ID and appear in owner history. Viewer restrictions and the existing source/account/business-row checks still run. Final SQL checks require **exactly three** bound probe history rows: two initial successes and one recovered success. The failed request must add none.

The index is restored in a `finally` block after ordinary request/check errors. If a conflicting index appears, both versions are retained and the rehearsal fails rather than overwriting it. An abrupt termination of the runner itself may leave the retained file for inspection; automated crash recovery is not implemented here. The shared provider and original restore are never fault-injected.

## Verification and limits

Focused check: `python -m unittest tests.test_restored_retrieval_api -v`. The synthetic-provider integration test exercises real proxy/authentication, missing-file failure, unchanged history, restored retrieval and saved-result counts. Other tests verify mode admission, restoration after a body exception, occupied retained-file refusal and preservation of both versions on a restore collision. Generation is forbidden by the fixture.

Run `npm test` for regression checks. Native local-provider execution is separate evidence. The report records the fault type, HTTP statuses, recovery checks, successful query IDs and original-data preservation. It does not establish provider-outage recovery, independent/off-host monitoring, load capacity, protected history, generated-answer accuracy or production readiness. No dashboard deployment or production requirement is accepted by this rehearsal.
