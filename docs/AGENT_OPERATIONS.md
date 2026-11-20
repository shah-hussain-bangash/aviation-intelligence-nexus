# Investigation operations

Administrators can select **Workflow operations** in the connected-research toolbar to open the new **Investigation operations** panel. It provides current saved queue counts and bounded recent execution observations. It changes no account credentials, database schema, worker execution rules or existing 64 workspaces.

## What is observed

`GET /api/v1/research/agent-operations` requires a signed-in administrator. Researcher/viewer access is rejected before reading the snapshot. It is a fixed read-only route; the dashboard proxy rejects writes and arbitrary subpaths.

Only records explicitly marked `local-background-queue-v1` are counted. Synchronous engineering runs are excluded. State totals cover all retained background records: waiting, running, awaiting review, reviewed as research, needs changes, failed, interrupted, cancelled and unknown. Active ages come from aware creation/start timestamps. Missing, naive, malformed or future timestamps remain unknown. An active age is not a cancellation deadline or evidence that a run is stuck.

The worker observation comes from the current API worker's enabled/alive/error/poll status. Disabled, unavailable, active, idle and unknown are distinct. Idle requires a recent poll within five seconds. A worker executing an investigation may not poll the queue again until that work ends, so a long poll age while active is not automatically declared a failure. This is not an independent observer or proof of successful model generation.

## Recent window and timing

The recent window contains at most 200 most recently updated background runs. Review updates can change membership; it is not a calendar-day or immutable event window. Per-tool counts distinguish attempted, completed and failed/unfinished steps across that window. A completed tool does not imply a semantically correct report.

Draft coverage counts are the saved boolean flags for awaiting-review/reviewed/needs-changes records with a recorded report fingerprint. They are labelled **recorded**, are not recomputed in this read-only view and must not be used as accuracy or current source-integrity claims. The existing research-review route rechecks the evidence separately.

Tool time is the sum of finite, non-negative recorded step times for terminal runs whose steps all have a timing value. Boolean/missing/invalid values are excluded. No-step and incomplete-timing records are counted as not recorded. The p50/p95 values use the nearest-rank definition, with maximum and sample size shown. Queue waiting, model planning/generation and human review are excluded. These are not end-to-end response times, a capacity estimate or an SLA. Review time is never inferred from the mutable `updated_at` field.

## Bounds, privacy and failures

The snapshot uses an existing SQLite file in read-only/query-only mode and a consistent read transaction. There is one snapshot slot per process, a 200-row recent window, a 64-active-record observation bound and a cooperative three-second SQL/Python observation budget. SQLite progress checks enforce the query deadline and busy waits are bounded. Path, SQL and filter parameters are not accepted from callers. The `flights` table, model artifacts and external providers are not queried.

SQL projects only state/timestamps, coverage-field types and tool name/state/elapsed-time fields. Owner identifiers, usernames, objectives, arguments, claims, review notes and raw failures are omitted from the response/export. Worker errors become a boolean signal. Snapshots are not written to a new store; this does not add protected telemetry or retention policies.

Missing/busy/corrupt/unavailable storage or a deadline returns safe HTTP 503 without queue counts or internal diagnostics. The UI clears previous figures while refreshing or after failure. It refreshes every 30 seconds and when the page becomes visible; snapshots older than 90 seconds or with irreconcilable future clocks are withheld. Export rechecks freshness. Sign-out or role change hides the panel, aborts pending work and invalidates late responses. Exports contain aggregate observations only. No jobs are cancelled, retried or modified by this panel.

## Verification

The full Windows suite passes 233 tests (185 Python, 48 Node); Linux skips the Windows DPAPI provider case. New tests verify count reconciliation, unknown ages, boolean timing rejection, nearest-rank quantiles, the 200-record window, worker states, byte-identical database content after observation, missing/busy/deadline/corrupt sources, administrator-only read access and safe errors. A temporary real queue/claim/runtime/review workflow with mocked provider replies verifies state transitions. It is separate from a real-user or actual-model production workload.

Six isolated browser component cases pass: desktop 1280, exact mobile 390, outage/recovery, session clearing with late responses, stale-response rejection and viewer hiding without a snapshot request. They use a clearly labelled synthetic aggregate fixture and the real component/styles. Export contents and screenshots were inspected. The fixture's timings/counts are synthetic examples, not production measurements. See `reports/Agent_Operations_Dashboard.json`.

Run `npm test` to repeat the automated suite. Source checks and deployment verification do not establish live administrator browser acceptance, independent uptime, worker failover, running-tool cancellation, external alert delivery, semantic AI quality or production readiness. All 24 production requirements remain open.
