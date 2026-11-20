# Saved background investigations

Current update: running investigations now support cooperative stop requests between bounded calls. See [cooperative stops](COOPERATIVE_INVESTIGATION_STOP.md). The queued-only cancellation description below records the initial milestone; current calls are still not forcibly interrupted.

The investigation desk now submits work to a SQLite-backed queue and returns HTTP 202 after saving it. The browser polls the saved run for progress; the AI workflow runs independently in one background thread attached to the local API. Acknowledgement means queued, not successful or approved. The existing tool restrictions, citation/coverage checks and report-bound human research review still apply.

## Use

On the Docker dashboard at http://localhost:8090, sign in as a researcher or administrator, load an example and choose **Run investigation**. Inspect the saved queued/running state, tool checkpoints and terminal report. Closing/reloading the page does not cancel saved work. After reloading, choose **Refresh saved investigations**, then open the run to resume observing it. History shows the latest ten accessible runs; an already-open run is polled by its UUID.

**Cancel queued investigation** works only before a worker claims it. If execution has started, cancellation is rejected; the local tools are not forcibly stopped. Polling failure does not start another job or imply failure of the saved execution. Changing inputs or signing out clears the displayed result/polling, not server work. A research review applies no airline action.

Docker Compose enables the worker with `AIN_AGENT_JOBS=1`. The native `npm run dev:all` launcher defaults that flag to 1 for newly started services; an existing API needs restarting to load the flag/code. Set the flag to 0 explicitly to disable background execution. The new UI then disables submissions and preserves saved-report access. The legacy synchronous endpoint remains available only when the background worker is disabled, for compatibility with the earlier bounded API.

## Execution and duplicate controls

- At most one investigation runs, with up to five waiting globally and two waiting per owner. Excess waiting requests return 429.
- An owner/request key is unique; retrying that key with changed inputs returns 409. Matching retries return the existing run. Identical inputs already queued/running for the same owner reuse that active run even if the request key differs. Up to 32 additional retry keys are persisted per active run and survive worker checkpoints/completion; excess aliases are rejected. An unrecognized new key after terminal completion intentionally allows a new investigation; this is not a general exactly-once guarantee.
- A submission whose browser response is lost retains its request key in that page's memory for retrying unchanged inputs. Page reload loses that retry cache; inspect saved history before submitting again. No credential or research-input cache is added to browser storage.
- Claiming uses a SQLite write transaction, checks FIFO waiting order and rechecks the current account's active status and researcher/admin role. Revoked/demoted accounts' waiting jobs are cancelled. Role changes during an already running read-only investigation do not forcibly interrupt it.
- Admins can inspect/cancel queued jobs across local accounts; other users see only their own runs. New runs and cancellation require researcher/admin access, Origin and CSRF checks. An unknown/inaccessible run returns 404.

The queue uses the existing `agent_runs` table and schema 7; no schema or credential migration is needed. It reuses the same run ID for execution and stores checkpoints in the same database rather than creating a second report. Inputs, actor ownership, results and failures remain private research records excluded from Git.

## Restart and restore

On an ordinary API restart, queued jobs remain queued and may execute after startup. Previously running investigations are marked interrupted and are not automatically replayed. On backup restoration, both running and queued work are stopped: restored queued jobs become cancelled so a second restored instance does not replay them. The original database is unchanged by restoration. Existing backup row counts still reconcile because state transitions do not remove run records.

The worker is part of one local API process. Do not run multiple API replicas/workers against this database: startup recovery is not a lease-based failover protocol and can conflict with another live process. Operator evaluation scripts must not run concurrent investigations against the active service database. Graceful shutdown waits for the current bounded execution; Docker/OS termination can interrupt it, with the next startup retaining checkpoints and marking interruption. The existing 120-second deadline uses bounded calls and cooperative checks; it is not forcible process cancellation or a hard real-time guarantee.

## API

- POST `/api/v1/research/agent-jobs`: Investigation JSON and UUID `Idempotency-Key`; 202 saved/replayed run, 429 waiting limit, 409 conflicting key, 503 unavailable worker/storage.
- GET `/api/v1/research/agent-jobs/{run_id}`: owner-scoped current result/checkpoints.
- POST `/api/v1/research/agent-cancel`: `{"run_id":"UUID"}`; queued-only cancellation, 409 if already running/terminal, idempotent for already-cancelled work.
- Existing agent status reports worker enablement/liveness, last poll and queue limits. Existing history, export and review endpoints continue to work.

The fixed dashboard proxy permits only the UUID read route and fixed submission/cancellation routes; browser requests cannot choose a backend, SQL query or tool destination.

## Evidence and remaining work

The full Windows suite passes **147 tests: 121 Python and 26 Node**; Linux explicitly skips the Windows DPAPI provider test. Queue tests cover competing claims, deduplication/conflicts, limits, permissions, cancellation, restart, backup restoration, runtime checkpoint reuse, failure sanitization and API access. Actual local Ollama execution and browser reload/cancellation are recorded separately in [the evidence report](reports/Background_Investigations.json).

This is a bounded single-process research worker, not an external durable worker platform. Distributed leases, independent worker isolation, retry/dead-letter policies, per-tool running cancellation, scheduler/alert ownership, long-term retention/capacity tests and cloud failover remain incomplete. A passed mechanical coverage check still needs human relevance/semantic review. No production readiness or general agent reliability is established.
