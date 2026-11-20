# Local service monitoring

The administrator dashboard now includes **See what needs attention**. It reads the authenticated `/api/v1/research/monitoring` endpoint. Anonymous access returns 401; researcher/viewer access returns 403. Account credentials and the 64 workspaces are unchanged.

## What is measured

With `AIN_MONITOR_ENABLED=1`, the API samples three fixed components at startup and every 30 seconds after the preceding sample completes:

- Database: schema-version query succeeds and matches this release.
- Active model: the v2 file checksum matches its experiment report.
- Local AI: Ollama lists both configured embedding and chat models.

These are availability/integrity probes, not end-to-end prediction or generation, database corruption scans, model quality checks or proof of an airline service objective. An unavailable component makes the sample degraded. A sample older than 90 seconds becomes unknown and its component badges are withheld. Missing samples are never reported healthy. The browser refreshes every 30 seconds while an administrator is signed in; refresh failure clears the previous display.

API middleware records completed response status classes and a rolling p95 latency over at most 200 requests. Counts include API authentication/validation failures; successful monitoring polls and health endpoints are excluded. HTTP 5xx responses retain at most 50 timestamp/status records. A model-generated agent failure returned in a successful HTTP response is not an HTTP error: this milestone does not count semantic AI failures. Latency measures API middleware response time, not browser network time, and includes research/identity requests of different durations. It is not a latency service objective.

Component transitions retain the latest 50 entries, with initial unavailability and later recovery distinguished. No request bodies, question text, URLs, query strings, usernames, passwords, tokens, cookies, IP addresses or exception details are recorded by this monitor. Application/server access logs are separate and not qualified by this statement.

## Persistence and lifecycle

Every component sample writes a bounded JSON snapshot atomically to `monitoring.json` in the instance's private state directory. It includes current process counts and recent events. Failed writes appear as degraded storage status. The file is excluded from Git and is derived monitoring state, deliberately excluded from the four-file recovery snapshot. It is ordinary unencrypted local storage, not a protected audit.

Counters, latency samples and transitions reset on process restart. The previous file is not loaded as current health. A new process reports unknown until its own first sample completes, then replaces the latest local snapshot. Recent events can therefore be lost on restart or between samples. Shutdown waits for an in-progress bounded probe/write rather than leaving a background write running. There is no independent observer while the API or workstation is stopped; browser polling can only report that monitoring is unreachable.

## Enable and inspect

Docker Compose enables sampling in the API service automatically. Open http://localhost:8090 and sign in using your existing administrator account. The monitor is hidden from other roles and the API enforces this permission independently.

For native development, set the flag before starting the service:

```powershell
$env:AIN_MONITOR_ENABLED = '1'
npm.cmd run dev:all
```

Restart an already running API for the flag or code to take effect. Without the flag, request counters still work, but component sampling and snapshot persistence are disabled; the dashboard labels that state explicitly. Monitoring performs no operational actions and sends no messages or external alerts.

## Verification and limits

Tests cover stale/disabled/initial state, failure-to-recovery transitions, probe exception redaction, snapshot-write failure, bounded retention, restart behavior, background start/stop, actual API model-unavailable HTTP 503, administrator permissions and proxy/UI behavior. The current complete suite contains **118 tests: 98 Python and 20 Node**. Synthetic isolated failures do not alter the real flight database or stop host Ollama. The local Docker instance is also checked against its real model/database/model-service availability and background snapshot updates. See the [evidence report](reports/Local_Monitoring.json).

Remaining work includes independent uptime monitoring, protected centralized logs/metrics, alert delivery and ownership, acknowledgement/escalation, service objectives, long-term history, semantic AI quality/drift monitoring, tracing, production load tests and cloud deployment. Local monitoring does not qualify the system as production-grade.
