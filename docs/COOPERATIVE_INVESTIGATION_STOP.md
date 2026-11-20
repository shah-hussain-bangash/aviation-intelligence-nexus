# Cooperative investigation stops

Researchers can open an owned active investigation and choose **Request stop**. Admins can also stop other users' investigations; viewers cannot submit stop requests. Queued work still offers immediate cancellation. Existing account credentials and saved completed reports are unchanged.

## State and evidence

`POST /api/v1/research/agent-cancel` retains the existing authenticated, same-origin, CSRF-checked endpoint. An accepted running request returns HTTP 202 with `state=running`, `cancel_requested_at` and `cancel_requested_by`. Repeated requests preserve the first requester/time. The dashboard disables the pending button and polls until a terminal state is saved. An acknowledgment is not proof the investigation has stopped.

The worker checks saved stop markers at boundaries before and after planning, tools, summary and repair calls. It does not kill a thread, process or provider request. A current bounded call may finish. On observing the marker it saves `state=cancelled`, retains completed/failed tool observations and timing, removes generated claims, quality and the report fingerprint, and prevents review. The JSON export retains this evidence and stop metadata. A not-yet-executed checkpointed tool is labelled `cancelled_before_execution`. This cooperative mechanism does not promise an instantaneous stop or an absolute completion deadline, particularly when SQLite or the provider is unavailable.

The final report checkpoint and stop request serialize through SQLite write transactions. If the stop commits first, a stale final checkpoint cannot publish an awaiting-review report. If the completed report commits first, stopping returns HTTP 409 and leaves that report intact. Stop metadata and submission aliases survive runtime checkpoints. Old browser poll responses cannot overwrite a newly acknowledged stop request. A lost stop response triggers state reconciliation rather than a fresh investigation.

Queued cancellation returns HTTP 200; repeated terminal cancellation is idempotent. Foreign-owner access remains hidden with HTTP 404; insufficient role returns HTTP 403. Existing unauthorized/CSRF checks remain in force. Restarted running work becomes `interrupted`, including when a stop marker exists, and is not automatically replayed. Reusing a completed request key returns the saved result.

## Verification

Eight isolated Python tests cover ownership/roles, idempotency, stopping before initial discovery, requests during planner/tool/summary calls, evidence retention, the final-commit race, stale checkpoint metadata, restart behavior and the authenticated HTTP contract. Three additional rendering tests cover pending, cancelled and interrupted states. Six isolated browser scenarios cover desktop, 390px mobile, queued cancellation, viewer restrictions, response-failure reconciliation and session clearing. Those browser responses are simulated; they are not user-account or provider executions.

`reports/Cooperative_Stop.json` records one actual local Qwen3 engineering execution in a separate database. Its current planner call returned normally, then the runtime stopped before any tool or summary. Replaying the request made no additional provider call. Tool-in-flight and report-save races are verified by controlled tests, not by this single live-model run. This is not a latency benchmark, broad task evaluation or independent acceptance. Private failed setup attempts remain under `.local`; no real user's work was stopped for these checks.

Reproduce with `python -m agents.evaluate_stop --output .local/new-stop-experiment`. The installed local Ollama service and `qwen3:8b` must be available. The command requires a new private output directory and publishes nothing automatically.

## Remaining production work

One local worker, five global waiting jobs, two waiting jobs per owner, three planner/tool calls, two summary attempts and the existing cooperative 120-second budget remain unchanged. External worker isolation, distributed leases/failover, forced interruption, managed monitoring/alerts, semantic task evaluation and operational acceptance remain outstanding. All 24 production requirements remain open.

The changed job/store/runtime files are already part of the release compatibility contract. Older rollback manifests require a new compatibility review; this change does not qualify a new rollback target. Existing historical model, optimization and recovery reports remain scoped to their recorded releases.
