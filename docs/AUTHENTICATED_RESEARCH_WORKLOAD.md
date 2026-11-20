# Disposable authenticated research-workflow drill

The native API can now be exercised over real loopback HTTP with disposable accounts, an empty flight database and a copy of the locally trained delay-v2 model. This adds authenticated prediction/history evidence beyond the anonymous HTTP sample. It does not measure the deployed Docker dashboard, full-dataset SQL scans, browser rendering, LLM/RAG/agent execution, sustained capacity or production performance.

## Repeat safely

From the repository root, with the trusted locally generated model available:

```powershell
.\.venv\Scripts\python.exe -m infra.research_workload --requests 12 --workers 2 --output .local/performance/research-new.json
```

Choose a new output filename. The tool refuses to overwrite existing results. `--model-directory` defaults to `.local/models/delay-v2`; use only an operator-trusted local joblib artifact. A matching report digest and research gate are checked before copying or loading. Matching a mutable local report is an integrity check, not a signature or a sandbox for untrusted serialized models.

There is deliberately no target URL, port, account password or live database argument. The tool binds a fresh IPv4 loopback socket on an operating-system-selected port, starts one native Uvicorn API there and uses a new temporary directory for all writable state. It copies only the model and its report, creates four disposable accounts (admin, two researchers and viewer) using a randomly generated password, and logs in through the actual HTTP endpoint. The background investigation worker and monitoring probes are disabled for this isolated app. No personal account or session is read or reused. The model source is read but never written.

The client uses fresh HTTP connections with a ten-second socket-operation timeout and a 2 MB response cap. Prediction-batch limits are 1–30 requests and 1–4 client workers. The duplicate-request race always uses two workers. This is a short bounded count, not a sustained workload or total-run time guarantee. A failed check raises an error instead of writing a passing report. Cleanup stops the temporary server and removes its database, account/session records and copied model; cleanup failure prevents a success result.

## Executed checks

- Disposable real password sign-in succeeds; anonymous history access is denied.
- A viewer cannot submit a prediction; missing CSRF is denied; unknown airport vocabulary is rejected.
- The first valid historical scenario produces a bounded research-only probability with the expected artifact identity.
- Same-key replay returns the same saved run. Changed input and another owner reusing that key receive conflicts.
- Concurrent unique requests reproduce the first probability and artifact identity and save results.
- Two concurrent requests sharing a fresh key produce exactly one saved run and one replay.
- The owner can read recent history; the other researcher sees no history. Exact database row count and SQLite integrity pass.
- Logout revokes the session; its former cookie cannot access history.
- The temporary server stops and its directory is removed before a successful receipt is returned.

The public receipt excludes passwords, cookies, CSRF values, account IDs, run IDs, temporary paths, response bodies and stack traces. It includes only the fixed historical scenario, public model identity, timing/count summaries and check outcomes.

## Observed trained-model run

On 20 November 2026, new harness code based on commit `8cf03d31769859bbbf183985143abbcb99f26ffb` ran in the normal Windows session. It used the actual trained delay-v2 artifact `71b23232edc615a01daee387e1e7dbb2c0aa3f7dae2b4d1f33fabbc0fbbff732`. The fixed AA/JFK/LAX scenario on 15 May 2025 at 09:00 produced probability `0.14414301173592028`, matching prior local research results. This is conditional historical US domestic research, not a prediction for a new Emirates flight or an independent model evaluation.

| Measurement | Observed result |
| --- | ---: |
| First prediction in the new API instance | 79.620 ms |
| Concurrent unique prediction requests | 12 |
| Client workers for that batch | 2 |
| Batch failures | 0 |
| Batch median | 24.624 ms |
| Batch p95 / maximum | 70.407 ms |
| Saved rows before disposal | 14 |

The fourteen rows comprise one initial prediction, twelve unique batch requests and one row for the duplicate race. Denied, conflicting and replayed calls add no rows. These timing summaries include authentication middleware, artifact verification, inference, history persistence and native loopback HTTP overhead. Account provisioning, sign-in, negative checks and duplicate-race requests are outside the timed prediction batch. The first call is cold only relative to this API's predictor cache: the OS/model-library caches may already be warm. Nearest-rank p95 for twelve requests is the maximum, so this small sample cannot estimate tail behavior reliably.

The actual receipt is [Authenticated_Research_Workload.json](reports/Authenticated_Research_Workload.json). All defined checks passed. No service-level performance targets were agreed, so `performance_target_assessed` and `production_ready` remain false. Short-burst throughput is not a capacity promise.

Three regression tests cover workload limits, corrupt-artifact refusal before deserialization, and the complete native HTTP workflow using a small synthetic trained fixture. The full Windows suite has 164 tests (137 Python and 27 Node); Linux skips the Windows-only DPAPI provider case. Hosted Python jobs run that fixture workflow, not this private trained artifact or real flight data.

Remaining qualification includes sustained deployed workloads, full-dataset contention, mixed authenticated users, LLM/agent queues and cancellations, resource measurements, agreed latency/error objectives, TLS/managed identity, browser/accessibility review and independent acceptance. The production readiness catalog remains open in all 24 areas.
