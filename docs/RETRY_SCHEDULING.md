# Persisted research retry timing and pause controls

Sixth new local data-platform increment, 24 November 2026. The synthetic ingestion runner now supports an explicit due-time extension, exponential retry delays and pause/resume controls. This implements scheduling policy for manual invocations; it does not install Windows Task Scheduler, start a background process or authorize any external dataset.

## Explicit case extension

`enable_schedule(case, base_delay_seconds=30)` runs under the existing case worker lock and adds `jobs.not_before` plus a versioned singleton control table to that case's separate queue database. The schema/control insertion is one SQLite transaction. No application database migration occurs. Existing cases remain unchanged unless this function is deliberately called; legacy workers retain their prior immediate replay/busy-retry behavior when no extension is present.

Enablement is idempotent for the same base delay, and a different delay is refused rather than silently replacing policy. A legacy case with a running job must recover it before enablement. A partial extension or invalid stored due-time/control data prevents scheduled claims. This is a local structural guard, not authentication against an OS owner who edits the database. The original synthetic marker, archive binding, single-host worker exclusion and three-attempt limit still apply.

## Due and pause behavior

The worker persists UTC epoch seconds in `not_before`. A queued job is eligible only when `not_before <= now`; the exact boundary is inclusive. Jobs are still chosen in sequence among eligible items, so a delayed retry does not block a later independent due batch. No inter-batch dependency is inferred.

Busy/locked imports are requeued with delays of `min(3600, base_delay_seconds * 2**(attempts-1))`. The base delay must be 1–3,600 seconds. At the existing three-attempt limit the job is quarantined. State and the next due time commit together in the queue database. The import transaction remains separate from acknowledgment, with the earlier replay-safe recovery semantics.

For real manual invocations the delay begins at the later of claim and completion clock readings. An interrupted scheduled job discovered under a released worker lock is requeued with one delay from discovery time; subsequent idle ticks do not keep extending it. Exhausted interrupted jobs are quarantined. This prevents a rapidly restarted worker from repeatedly consuming attempts without waiting.

`pause_schedule(case, True)` prevents new claims and interrupted-job recovery without changing attempts. `False` resumes eligibility. Pause acquires the same nonblocking worker lock, so it cannot interrupt an active import; a busy error means the caller must retry the pause between jobs. `schedule_status(case)` reports paused state, queued/due/eligible counts and the earliest queued due time. Due counts describe time eligibility; paused cases have zero eligible jobs.

The `now` keyword on worker/status functions accepts explicit integer epoch seconds for deterministic research tests. Normal calls use the host UTC clock. Backward movement leaves future jobs waiting; forward wall-clock changes can make them eligible earlier in elapsed real time. The protocol is not a monotonic distributed clock or a guarantee under clock tampering. Unsupported epoch values and delay overflow are refused, rather than silently shortening a delay.

There is no sleeping loop, jitter policy, supervisor, holiday calendar, external alert or service availability guarantee. The caller must invoke the worker after a job becomes due. Blocked/quarantined jobs still require review; pause and backoff do not approve or repair them. No background task is installed by these functions or the demonstration.

## Reproduce the policy checks

```powershell
.\.venv\Scripts\python.exe -m pipelines.verify_retry_scheduling
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_retry_scheduling.py -v
npm.cmd test
```

The command accepts no existing case/database path. It creates new synthetic cases under `.local/retry-scheduling/<case_id>/`. Busy errors are deliberately injected and time is explicitly controlled; these are policy tests, not measured database contention or elapsed waiting. A separate process reads the persisted due-time status. The earlier crash demonstration remains the evidence for actual abrupt-process recovery and OS lock release.

Thirteen demonstration checks cover deferred retries, an independent due batch, an early tick, cross-process due-time persistence, pause/resume, 30/60-second backoff, attempt exhaustion and delayed recovery from an injected interruption. The successful case ends with four synthetic flight identities, two import ledgers and zero observed BTS rows. Its exhausted and interrupted companion cases are retained for inspection.

The report records source revision/dirty state where available, selected participating source hashes, fixed fault labels, queue states and timing observations. Previous cases, historical flight data, frozen models and the running dashboard are not selected or modified. Scheduled execution supervision, real data/source approval, representative retry/recovery load, independent operational monitoring and final-image qualification remain open. This change does not complete the data platform or establish production readiness.
