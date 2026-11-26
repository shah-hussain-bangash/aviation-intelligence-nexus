# Case-bound local investigation jobs

The opt-in API and dashboard bind a new queued investigation to an owner-saved research case version. The dashboard currently submits the fixed recorded input-distribution tool scope. Operational actions, shared cases and production qualification remain open. Existing workspaces and normal release startup are unchanged.

Use the explicit native [case workspace factory](RESEARCH_CASE_WORKFLOW.md) with its chosen separate state directory. Enable its existing local worker by setting `AIN_AGENT_JOBS=1` before starting that factory. This does not enable the feature in the running Docker release. A fresh workspace requires its own account and an authorized saved prediction/case; tests seed clearly synthetic examples. Keep case data, account passwords, sessions, logs and generated reports out of Git.

## Dashboard sequence

Select your case under **From prediction to investigation**. The **Investigate this case** panel appears with its title and current version. On an open case, an admin/researcher can enter an objective (12–600 characters), optionally choose the comparison example, acknowledge local AI use and select **Start case investigation**. New submissions require the recorded January–March versus May 2025 distribution-evidence tool; simulation and peer sharing are disabled in this form. These aggregate comparisons do not explain an individual flight. Case notes are not automatically sent to the model.

Choose a saved run or use **Refresh investigations** / **Refresh selected run** to read checkpoints. Updates are manual; reading, selecting and refreshing do not rerun AI. The panel shows captured versus current case versions, state, tool checkpoints, saved quoted findings, automatic coverage status and an escaped JSON inspector. A completed draft is explicitly **Unreviewed** until a research review is recorded through the existing investigation controls. Automated coverage is not human assessment. This panel neither records a review nor attaches the report automatically.

**Request investigation stop** cancels waiting work or requests a cooperative stop for a running call. An in-flight call may finish. Refresh to confirm the final saved state; cancellation retains completed evidence and removes any reviewable draft. Stop controls are disabled once a request is pending or the run is terminal. A closed case still permits reading/cancelling eligible owned jobs; new submissions are hidden. Viewers have read controls only for cases/jobs they own.

After an uncertain submission, the form keeps the same request key and body in memory, locks edited inputs and offers **Retry same submission**. It does not retry automatically. A changed response, permission failure or conflict clears unverified output and requires inspecting refreshed state. Keys are not persisted across sign-out/reload; inspect saved runs before starting again after either. Switching case, changing its version or signing out aborts in-flight display requests and clears the previous client context. Late responses cannot repopulate a different case/session. Leaving the view does not cancel saved server work.

Synthetic browser verification covers deliberate acknowledgement, real local Qwen execution, retained draft reload, older-version labelling, an isolated API outage and retry, running cancellation, viewer-owned reads and sign-out cleanup. Small-screen checks cover the new panel; they do not qualify site-wide accessibility or production use. Fixtures/reviews are labelled separately from genuine human acceptance.

## Authenticated API sequence

Sign in normally and use the returned session cookie, CSRF token, allowed Origin and a fresh UUID `Idempotency-Key`. Passwords are entered privately through the normal sign-in flow. Then:

1. GET `/api/v1/research/cases/{case_id}` and inspect the current open case/version.
2. POST `/api/v1/research/cases/{case_id}/jobs` with the observed version and an existing bounded investigation request. For example:

```json
{
  "expected_version": 1,
  "investigation": {
    "objective": "Inspect the recorded historical input-distribution evidence for this research case and retain its limitations.",
    "month": "2025-05",
    "required_tools": ["distribution_evidence"],
    "include_distribution_evidence": true
  }
}
```

3. A 202 response records the queued run and its server-created `request.case_context`. GET `/api/v1/research/cases/{case_id}/jobs` lists up to ten recent owner jobs; GET `/api/v1/research/agent-jobs/{run_id}` reads checkpoints/results. Use the existing owner cancellation endpoint for a queued/running job. No tools run in the submission handler.
4. Inspect any completed draft and its evidence. Existing review is still explicit; a saved research review does not approve airline operations. A reviewed/needs-changes report can be attached through the existing case attachment API, at the case's current version. A case-bound report cannot be attached to a different case. Submission itself does not change the case version, add an event or auto-attach a draft.

No arbitrary context, owner ID, executable tool, URL or path can be supplied through these routes. Both generic and nested investigation models reject a client-provided `case_context`. Case-bound jobs currently reject `require_peer_review=true`: sharing a case's metadata needs a defined permission model. The existing generic second-account workflow is retained for unbound reports.

## Version and transaction rules

The server records case ID/version, a SHA-256 of the validated full case projection, title, saved prediction ID/fingerprint and research scope. This is bounded identifying metadata, not a retained copy of all case notes or attachment contents. Notes are not automatically sent to the model. The title and metadata enter the planner's user-data message and confer no tool authority. Keep the paired case store if a reviewer must reconstruct the full context.

Submission locks the primary database first, rechecks the account's current active role, then locks the case store. Ownership, openness and observed version are validated and the metadata is frozen. The case guard stays held until the primary queue transaction commits. There is no distributed write or new case event: only the primary job record is written. Schema versions remain primary 8 and cases 4.

The context participates in the request fingerprint, active-job deduplication, every checkpoint and final report/review hash. Same inputs and key replay the saved job, including after case closure; changed inputs/key reuse conflicts. Two cases cannot coalesce into one active job. The usual queue limits apply: five waiting globally, two per owner, one running; existing tool/provider deadlines and budgets remain in force.

Claiming rechecks the account and exact current case metadata/version before changing the job to running. Stale, closed or unavailable cases cancel waiting work without a provider call. A worker configured without the case service cannot execute a bound job. Database read/lock failures leave work unclaimed for inspection/retry rather than treating unavailable context as valid. Once a claim commits, later case changes do not rewrite or automatically stop the running investigation; its context is historical. Cancel explicitly when needed. Account deactivation or loss of researcher/admin role stops a bound run at the next cooperative boundary. An in-flight provider call is not forcibly interrupted.

Restart retains the original context and marks running work interrupted; it does not replay tools. Existing restore cancels restored waiting work. A new attempt must use an inspected case version and a new submission key. A checkpoint that removes or changes a bound request is rejected.

## Privacy and evidence limits

Bound jobs stay owner-only through case listing, job reads, recent history, archive, review and cancellation, including against another administrator account. Generic administrator access to unbound investigations is unchanged. The review inbox excludes bound jobs; aggregate operations counters contain no objectives or case metadata. Paired backup and encryption retain job JSON with the two stores; they do not replace source authentication or protected auditing.

Do not run older agent code against a workspace containing case-bound jobs: older history/archive policies may expose these request fields to another administrator. Rollback compatibility and final deployed recovery must be qualified for this new privacy contract; earlier receipts are historical. Filesystem owners can still alter both stores and hashes. The binding is consistency evidence, not independently authenticated provenance, genuine human assessment or model-quality acceptance.

Focused checks: `python -m unittest tests.test_case_jobs tests.test_jobs tests.test_agent_archive tests.test_case_agents tests.test_peer_review -v` and `node --test tests/test_research_cases.mjs`. Tests use synthetic accounts, predictions and review decisions. Provider responses in unit tests are mocked; the fixed recorded-distribution evidence tool is actually executed. Any separately recorded live local-model rehearsal must distinguish actual execution from useful output and genuine human review.

Still open: additional tool-scope controls, case sharing permissions, genuine review and combined useful-outcome acceptance, representative load, original-user/deployed qualification and all 24 production acceptance requirements. This increment does not make the whole case journey complete.

## Case-panel review and attachment

The opt-in local case panel now offers two separate actions for the selected owned job. A writer can explicitly record `reviewed` or `needs_changes`, with a 5–1000-character note and acknowledgement. The decision pins the displayed report hash. Acceptance requires automated coverage to pass; this is not an assessment of usefulness. Viewers cannot write reviews or attachments.

Attachment first reads the current case, selected saved report and eligible owned source. It refuses a changed displayed case version or review, then submits the server-issued snapshot fingerprint with the displayed expected version. A successful attachment advances the case once and retains the review state, including `needs_changes`. The original captured job version remains visible. Closed/full cases and already-attached runs offer no attachment action. No review automatically attaches a report or applies an airline action.

After a timeout, refresh cases and inspect the saved run before another review or attachment; the review endpoint is not an idempotent retry API. Case/session changes clear the panel, and an obsolete attachment preflight cannot proceed to its write. The server remains authoritative for ownership, permission, report integrity and version conflicts.

Focused dashboard checks: `node --test tests/test_research_cases.mjs`. Browser rehearsal uses disposable synthetic accounts and an explicitly labelled recorded-evidence fixture. Its needs-changes decision tests persistence only; it is not genuine human acceptance, a new provider run or production qualification. Existing credentials and the Docker release are unchanged.

## Combined deterministic API rehearsal

Run from the repository root, using a new private directory each time:

```powershell
.\.venv\Scripts\python.exe -m pipelines.verify_case_journey .local/case-journey-01
```

This creates only disposable synthetic accounts and fresh primary/case stores. It runs the real in-process API handlers through saved prediction → note → saved Q&A → bound investigation → explicit needs-changes review → retained report → computed synthetic gate proposal → closure. The report records all six case versions, case/report/snapshot fingerprints, source revision and code hashes. A second application instance verifies persistence.

Negative checks cover anonymous/CSRF access, unavailable-worker submission, changed report pins, stale case edits, duplicate attachment replay, closed-case writes, private access by another administrator, viewer writes and a temporarily missing case store. The missing store must return 503 without creating an empty replacement; the fixture restores its own file in a `finally` block. Existing target directories and paths outside the repository's private `.local` area are refused by the command.

Scope: the stored prediction and Q&A are synthetic fixtures. The distribution reader executes against the committed historical report, and the MILP solver computes a small synthetic proposal. Planner/generator calls and the background worker loop do not run: worker availability and agent checkpoints are explicit deterministic test fixtures. Review notes identify themselves as synthetic and use `needs_changes`; closing the case does not accept those findings. No browser, real network listener, existing user database, deployment, real-user acceptance, representative load or production qualification is exercised. The temporary databases contain synthetic authentication material; keep the entire fixture directory private and out of Git.

The CLI exits nonzero on failure and writes `report.json` only inside its newly created directory. Reports distinguish the prediction snapshot fingerprint from the code-hash map. Run `python -m unittest tests.test_case_journey -v` for focused regression checks. This combined state/permission rehearsal supplements the separate live-provider and browser evidence; it does not replace them.

## Explicit live local-AI rehearsal

To exercise the real local worker instead of deterministic checkpoint fixtures, opt in with a fresh directory:

```powershell
.\.venv\Scripts\python.exe -m pipelines.verify_case_journey .local/live-case-journey-01 --live-ai
```

This mode requires the existing approved loopback Ollama service and installed `qwen3:8b`; it never downloads a model or chooses a remote provider. It starts the real worker loop for the fresh case, submits through the API, and reads saved checkpoints for up to 150 seconds. It does not call `claim` manually or seed the report. Instrumentation wraps the actual planner, generator and tool functions without supplying responses. The report checks the saved model digest, exact case/report fingerprints, actual distribution checkpoint, successful call counts within the existing 3-planner/2-generator/3-tool budgets, automated coverage, and worker shutdown. Existing runtime call deadlines and safe-boundary cancellation still apply; a wait deadline is not a forced provider interruption.

The same six-version case journey, explicit synthetic needs-changes decisions, attachment replay, dependency and role checks follow. Predictions/Q&A/reviews remain synthetic fixtures; only the approved local AI worker, recorded-evidence tool and synthetic MILP actually execute. This does not prove prediction inference, retrieval, semantic usefulness, genuine human assessment, a real HTTP listener/browser journey, representative load or production readiness. Default runs and CI remain deterministic and require no model service. Failed live reports mark execution fields unconfirmed (`null`) rather than claiming a stub or successful execution; inspect their retained private checkpoints before retrying into a new directory.

## Private usefulness review of a completed live case

`python -m pipelines.case_usefulness_review prepare --journey .local/LIVE_RUN/report.json --journey-sha256 EXACT_FILE_SHA256 --output .local/NEW_REVIEW_FOLDER` reads only the explicitly pinned rehearsal report and its retained case store opened with SQLite `mode=ro`. It verifies case/report/attachment fingerprints, the captured model and exact supporting evidence before exporting a self-contained `review.html`, `packet.json` and blank `annotations.json`. It never reads account credentials or writes a review into the case database. Existing output folders are refused. Keep the generated packet private and open the HTML yourself in a browser that supports local files.

The page preserves the earlier fixture's needs-changes label and starts all new ratings blank. Inspect each citation and rate support, relevance/usefulness and whether the objective was answered; add your label, notes and source/own-assessment declarations. Uncertain or incomplete ratings remain pending. `Show review JSON` displays the exact file content to copy/save; `Download my review JSON` requests a local browser download. The visible JSON fallback is browser-tested; the automated browser download check stalled and remains unverified. The page's content policy blocks connections, forms, objects and external resources; it performs no server submission or case mutation. Ratings remain only in memory until you save them.

Validate saved declarations with `python -m pipelines.case_usefulness_review assess --packet PACKET_PATH --packet-sha256 EXACT_PACKET_SHA256 --annotations SAVED_REVIEW_PATH --annotations-sha256 EXACT_REVIEW_FILE_SHA256`. Changed bindings, citations, inventories or unsupported ratings are rejected. Outputs are `pending`, `declared_needs_revision` or `declared_acceptable`, with identity verification, independent review, operational approval and production readiness all false. A local filesystem owner can fabricate both files and hashes; these are unsigned consistency checks, not authenticated human acceptance. The agent must not supply genuine ratings for the user.

Focused checks: `python -m unittest tests.test_case_usefulness -v` and `node --test tests/test_case_usefulness.mjs`. Unit/browser ratings use explicitly synthetic test labels and are not human assessment evidence. Browser UI checks use a separate fully synthetic localhost page: the browser tool disallows `file://` access, so the private live-case HTML was not opened by the agent. No live case content was served as a workaround.
