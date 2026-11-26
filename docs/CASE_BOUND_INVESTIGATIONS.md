# Case-bound local investigation jobs

This opt-in API increment binds a new queued investigation to an owner-saved research case version. It does not add a dashboard submission form, operational actions, shared cases or production qualification. Existing workspaces and normal release startup are unchanged.

Use the explicit native [case workspace factory](RESEARCH_CASE_WORKFLOW.md) with its chosen separate state directory. Enable its existing local worker by setting `AIN_AGENT_JOBS=1` before starting that factory. This does not enable the feature in the running Docker release. A fresh workspace requires its own account and an authorized saved prediction/case; tests seed clearly synthetic examples. Keep case data, account passwords, sessions, logs and generated reports out of Git.

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

Still open: dashboard controls for case-bound submission/monitoring, sharing permissions, genuine review and combined useful-outcome acceptance, representative load, original-user/deployed qualification and all 24 production acceptance requirements. This increment does not make the whole case journey complete.
