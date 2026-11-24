# Local foundation: request correlation and safe error telemetry

Every API request handled under `/api/v1/` receives a new server-generated UUID v4 in `X-Request-ID`. Caller-supplied request IDs are ignored. Early identity, Origin and CSRF rejection responses are covered. Unhandled exceptions before response preparation become a generic 500 JSON response with the same request ID; exception text and traceback are not returned or included in the structured event. Expected domain errors keep their existing handlers and statuses.

The Node gateway preserves a valid backend UUID v4 on allowlisted API responses. Local proxy rejections, malformed replies, missing/invalid backend IDs and unavailable dependencies receive a generated gateway ID. A proxy-unavailable error contains that gateway ID in both header and JSON body. Incoming browser request IDs are not forwarded. Gateway-only IDs do not establish a backend trace for timeouts or failures before a backend response exists; distributed tracing remains outstanding. Unknown frontend routes outside the proxy allowlist are not covered by this increment.

## Enable the local structured log sink

From the repository root in a separate terminal, select a fresh disposable state directory. These settings apply only to that terminal's child processes:

```powershell
$requestCheckRoot = Join-Path (Get-Location) ('.local/request-check-' + [guid]::NewGuid().ToString('N'))
$env:AIN_STATE_ROOT = $requestCheckRoot
$env:AIN_DB_PATH = Join-Path $requestCheckRoot 'ain.sqlite3'
$env:AIN_AGENT_JOBS = '0'
$env:AIN_MONITOR_ENABLED = '0'
$env:AIN_INTAKE_OVERVIEW_MOUNTED = '0'
$env:AIN_CONTAINER = '0'
$env:AIN_API_PORT = '18002'
.\.venv\Scripts\python.exe -m uvicorn services.api.main:app --host 127.0.0.1 --port 18002 --log-config infra/request-logging.json --no-access-log
```

If port 18002 is occupied, stop and select a different unused lab port; do not stop an unrelated process. Close the lab terminal after verification. Native logging uses the explicit configuration above. Newly built API images enable this configuration and disable Uvicorn access logs by default; existing deployed containers are not updated by source changes. The `ain.requests` logger emits one JSON event containing only event type, UTC timestamp, server request ID, method, source-defined route template, response status, response-preparation time and outcome. Route parameter values, raw URLs/queries, body text, cookies, passwords, authorization headers, user identities and exception messages are excluded. Early rejections use `unresolved_api_route`. Disabling the Uvicorn access logger prevents query duplication there; this is not a guarantee about every dependency's logging.

`api_response_prepared` measures preparation up to response headers, not completion of streaming delivery, client receipt, uptime or an end-to-end service objective. Failures after streaming has begun are outside this exception-conversion boundary. Telemetry emission is best effort; a broken optional log sink does not fail research requests. These records are local diagnostic metadata, not protected/tamper-resistant audit, authenticated identity evidence, durable centralized retention or external alerting.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_request_context -q
node --test tests/test_request_ids.mjs
npm.cmd test
```

Backend cases cover success and 401/403/422 failures, unique parallel IDs, caller-ID rejection, sanitized unhandled errors, route-template privacy and log-sink failure. Gateway cases cover valid-ID propagation, invalid-ID replacement, local method/query rejection and correlated unavailable responses. Tests use synthetic requests, disposable users and temporary databases. No real credentials, primary database mutation, deployment or production acceptance is required or claimed.
