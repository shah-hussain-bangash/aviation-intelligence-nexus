# Local HTTP performance measurements

This milestone adds a reproducible, bounded HTTP correctness and latency check. It does not establish airline workload capacity, browser rendering speed, authenticated workflow performance or production acceptance.

## Repeat the check

Start the local Docker release and verify its identity and health first:

```powershell
.\.venv\Scripts\python.exe -m infra.verify_deployment
.\.venv\Scripts\python.exe -m infra.load_check --port 8090 --requests 30 --workers 2 --output .local/performance/new-measurement.json
```

Choose a new output filename each time. Existing evidence is never overwritten. The standard-library client connects only to IPv4 loopback and uses exactly three allowlisted anonymous GET endpoints: `/`, `/__ain/ready` and `/api/v1/auth/session`. It sends no credentials/cookies and never follows redirects. It checks the AIN HTML title, backend readiness with production readiness false, and an explicitly signed-out session. These are content checks, not cryptographic server authentication; confirm the expected deployment before running.

There is one unmeasured warmup per endpoint, followed by its measured batch. Endpoints run sequentially. Each measured request opens a fresh connection; a thread pool bounds concurrent client requests. CLI bounds are 1–100 requests per endpoint, 1–4 workers, a 0.1–5 second socket timeout and a 2 MB response-body cap. A failed warmup stops subsequent batches. Measured errors remain in the counts and latency distribution; all remaining scheduled requests in that bounded batch finish. The timeout applies to blocking socket operations, not a total-run deadline.

No login attempts, scenario predictions, saved research, SQL metrics, optimizations or AI generation are triggered. Ordinary web access logs and existing response monitoring can record the GET requests. The client stores only timings, status codes and fixed error classes, never response bodies, cookies or exception text.

## Observed workstation sample

On 20 November 2026, the normal Windows session measured Docker Desktop at loopback port 8090. API and web were both running source revision `03ddbbfca7da01aa13a48bac86ef60d7e3fc3e8c`; all sixteen deployment health/isolation checks passed beforehand. The measurement harness was new working-tree code based on that revision. The database contained the existing 2,835,101 historical flight rows, but these anonymous endpoints do not scan that dataset.

The recorded sample used two client workers, thirty measured requests per endpoint and one warmup per endpoint (93 total requests). All 90 measured responses passed status and content checks:

| Endpoint | Measured requests | Failures | Median ms | p95 ms | Maximum ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dashboard HTML | 30 | 0 | 1.825 | 2.488 | 2.513 |
| Backend readiness | 30 | 0 | 4.028 | 14.710 | 26.546 |
| Signed-out session | 30 | 0 | 4.249 | 6.328 | 6.661 |

Raw measured summaries are in [Local_HTTP_Performance.json](reports/Local_HTTP_Performance.json). Percentiles use nearest rank, including failed-request durations if present. Completed requests per second divide all completed requests, including failures, by the client batch wall time. They are short burst observations, not sustained throughput limits. Warmups do not guarantee all service or database caches are warm. Loopback, OS scheduling, Docker and connection setup affect measurements; three-decimal formatting is not a precision guarantee.

There is no agreed latency/error service-level target, so the result explicitly reports `performance_target_assessed: false`. Its exit code checks only whether every measured response was valid; a slow successful response does not pass a performance budget that has not been defined.

## Regression and remaining work

The five synthetic-server/unit tests cover the real HTTP batch, content failures, fail-fast warmup, redirect refusal, oversized/invalid responses, signed-in leakage, bounded inputs and error-inclusive statistics. GitHub's container job repeats twelve measured requests per endpoint against fresh empty CI state. That hosted result is separate from this workstation/data sample, and its timings are environment dependent. Response summaries appear in the workflow log; the checked-in workstation report remains historical.

Still outstanding: agreed workload and service objectives; authenticated read/write and inference/agent measurements with safe disposable state; sustained and saturation tests; memory/CPU/queue/SQLite contention measurements; repeatability across hardware; browser asset/rendering and accessibility checks; independent review and production acceptance. Existing queue bounds and local rollback do not establish these properties.
