# Bounded foreground synthetic ingestion runner

Seventh new local data-platform increment, 24 November 2026. A foreground runner now invokes the scheduled synthetic worker repeatedly, waits between due checks and records clean stopping states. No service, operating-system task, cloud resource or background automation is installed.

## Explicit execution

```powershell
.\.venv\Scripts\python.exe -m pipelines.verify_ingestion_runner
```

This demonstration accepts no existing case/input/database path. It creates fresh cases under `.local/ingestion-runner/<case_id>/`, injects one synthetic busy failure and uses the real host epoch/monotonic clocks while the runner waits for retry eligibility. It also checks paused/stopped cases and resuming work left by a step limit. The report retains source revision/hashes, per-run observations and generated synthetic case state. Busy injection is deliberate; this is not an actual database-contention measurement.

For an explicitly created and scheduled **synthetic** case, the OS owner may instead run:

```powershell
.\.venv\Scripts\python.exe -m pipelines.run_synthetic_ingestion "<synthetic-case-directory>" --max-seconds 60 --max-steps 10
```

The case must pass the existing synthetic marker/path checks and already have its scheduling extension enabled. The runner never enables it automatically. Do not substitute the application state directory or a real-data folder. Markers and local controls prevent accidental use, not forgery by an OS owner. No web permission path is added.

## Execution and stopping policy

A separate nonblocking OS runner lock excludes a second participating foreground runner. The existing worker lock still protects each claim/import/acknowledgment. A direct manual single-job worker is not governed by the runner lock and can interleave between runner steps, so this is not exclusive ownership against all OS-owner tools or distributed coordination. Contention/errors end the run instead of starting an unbounded retry loop.

The runner checks stop, monotonic elapsed duration and result count between jobs; then it checks pause and calls the worker. The worker's persisted due-time policy remains authoritative. When work remains but no job is currently eligible, the runner sleeps for a bounded poll interval before checking again. Default polling is 0.25 seconds; library values from 0.05 to 5 seconds are allowed. OS load can delay wake-ups. Integer epoch eligibility has one-second resolution, and clock jumps retain the existing documented scheduling limitations.

`max_seconds` is an integer from 1 to 300. `max_steps` is an integer from 1 to 100 and counts returned worker results, including retry/terminal outcomes; it does not count distinct jobs. Limits are checked between batches. They are not hard import/IO deadlines and do not interrupt an active transaction. At the exact step boundary the runner conservatively reports `step_limit`, even if the last result happened to finish the queue; a subsequent invocation can establish drained state without re-importing succeeded jobs.

`request_stop(case)` writes a retained `stop.request` file. It can be requested while an import is active; the current call finishes, then the next boundary stops before another job. Existing stop requests are never cleared automatically. An operator must review and explicitly remove the request before restarting that case. The separate pause control retains its worker-lock behavior. Neither control approves, resets or deletes blocked/quarantined work.

## Recorded status

The latest `runner-status.json` is replaced atomically from a new private temporary file after work and waiting ticks and at exit. It contains a run ID, timestamps, configured bounds, a bounded list of worker outcomes, wait-cycle/requested-sleep observations and final state. Requested sleep is not measured actual elapsed sleep. A failed replacement can leave a temporary file; it is retained rather than deleted automatically. Status is a local latest snapshot, not authenticated audit history or independent liveness monitoring. Abrupt process termination can leave a historical `running` snapshot; no staleness or automatic supervisor restart claim is made.

| Final state | Meaning |
| --- | --- |
| `drained` | No pending work and all observed jobs succeeded; future enqueues are not watched |
| `needs_review` | No pending work, but blocked/quarantined work remains |
| `paused` / `stopped` | Cooperative exit without consuming more job attempts |
| `duration_limit` / `step_limit` | Invocation budget reached; pending work is retained |
| `interrupted` / `failed` | Execution interrupted or failed; inspect retained state before resuming |

The command returns zero for drained/paused/stopped and nonzero for incomplete, failed or review-required states. Ctrl+C is recorded as interrupted when Python can handle it; an interrupted worker may remain `running`, with subsequent recovery subject to the existing replay and backoff rules. Interruption does not prove that no data committed. No in-flight import is forcibly killed by the runner.

## Verification and limits

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_ingestion_runner.py -v
npm.cmd test
```

Twelve demonstration checks cover automatic due retry, recorded outcomes, completion-time consistency with a recorded due time, pause/stop, retained stop request, bounded/resumed execution, synthetic row/ledger counts and latest status/source consistency. The completion-time comparison alone is not a new independent oracle for exact claim time; focused scheduling tests establish inclusive eligibility. Tests also exercise a real timed idle exit, cross-process runner exclusion, stop requested during import, failures, interruptions and refusal of an unscheduled case.

Automatic-retry and bounded-resume cases retain three and four synthetic flight identities respectively, with zero observed BTS rows. Existing cases, historical data, frozen experiments and the running dashboard are not selected or modified. Production still needs supervised scheduling, independent health/alerts, real source approval, representative long-running load/recovery and final-image qualification. This bounded foreground executor does not close those requirements or establish production readiness.
