# Read-only runner snapshots and abrupt-exit recovery

Eighth new local data-platform increment, 24 November 2026. The bounded runner's latest file can still say `running` after an abrupt exit. A separate read-only inspector now distinguishes recent/stale running records and terminal records without asserting that the process is alive or the current queue is healthy.

```powershell
.\.venv\Scripts\python.exe -m pipelines.verify_runner_recovery
.\.venv\Scripts\python.exe -m pipelines.inspect_runner_status "<synthetic-case-directory>" --stale-after 60
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_runner_status.py -v
npm.cmd test
```

The demonstration command accepts no existing case/database path. It creates a new synthetic case under `.local/runner-recovery/<case_id>/`, starts a runner in a child process, and deliberately exits that process with code 74 immediately after its data import commits but before queue acknowledgment. The orphaned runner snapshot is copied unchanged to `orphaned-runner-status.json` for retained evidence.

The inspector accepts an explicit synthetic case path, validates its existing marker/path boundary and reads only `runner-status.json`. It does not open SQLite databases, take a runner/worker lock, write a report into the case, request a stop or change timestamps. Output includes a SHA-256 of the bytes actually read, recorded state/run ID, age, threshold, freshness and bounded result count. Operating-system access-time updates are outside the no-deliberate-write claim.

## Snapshot interpretation

| Classification | Meaning |
| --- | --- |
| `recent_running_snapshot` | Valid running record no older than the chosen threshold; process may already have exited |
| `stale_running_snapshot` | Running record older than that threshold; process may be stopped **or still executing a long batch** |
| `recorded_terminal_snapshot` | Valid recorded final state; newly enqueued work or later state changes are not inspected |
| `unavailable` | Missing, unsupported, oversized, malformed, future-dated or observably changed input |

Every result explicitly reports `process_liveness_verified=false`, `queue_state_verified=false`, `status_authenticated=false` and `production_ready=false`. A well-formed file can be forged by a privileged owner. Freshness and local hash consistency are not independent liveness, source authentication, an operational health check or permission to restart/kill a process.

The default threshold is 60 seconds and the accepted range is 1–3,600 seconds. The exact age boundary is inclusive. The runner does not heartbeat during an import, so a legitimate long-running call can produce a stale snapshot. The threshold needs an agreed workload policy before any operational use. A stale classification never triggers recovery, cancellation or task installation automatically.

The library's optional `now` parameter supports explicit test-clock observations and is recorded through `clock_override`; the CLI uses the actual host clock. The demonstration classifies the orphan at its recorded time and at that time plus 61 seconds, without pretending to wait a minute. Future status timestamps are refused. Clock changes and concurrent atomic status replacement can produce unavailable observations; callers should inspect/retry instead of declaring health.

The command returns zero for a valid recent-running or terminal snapshot, and nonzero for stale-running/unavailable. Zero means the snapshot was accepted for that classification, **not** that ingestion succeeded. A recorded failed/needs-review terminal state is still terminal evidence and must be interpreted through `recorded_state`.

## Bounds and recovery evidence

The inspector reads at most 128 KiB and rejects duplicate JSON keys/nonfinite constants, unknown fields/version, invalid flags, malformed timestamps/identifiers, unsupported states and bounded work-result violations. It compares file identity/size/modification observations across the read and returns a fixed unavailable error without private paths/raw exceptions. These are selected versioned shape checks, not a full semantic/authenticity proof or protection from hostile filesystem owners. No queue consistency or artifact/model verification is implied.

After inspection, the demonstration explicitly invokes a new runner. Operating-system exit has released both runner and worker locks. The interrupted job is deferred under the existing scheduling policy, then replayed through its already-committed import ledger. Final state retains three synthetic identities, one import ledger and zero observed BTS rows; its attempt count is two. Inspection alone never performs this recovery.

Twelve demonstration checks cover the real process exit, committed data, interrupted acknowledgment, orphaned status, recent-versus-stale classification, unchanged inspected bytes/directory entries, lock release, ledger replay, final counts and source consistency. Focused tests also cover missing/oversized/duplicate-key/bad JSON, future timestamps, invalid settings/outcomes, read-only input preservation and actual inspection CLI behavior.

The final snapshot still does not certify current queue health or liveness. Independent monitoring, supervised execution, representative failure/load cases, real source approval and final-image release qualification remain open. Existing research cases, historical data, frozen models and the running dashboard are not selected or modified by the demonstration. This increment does not establish production readiness.
