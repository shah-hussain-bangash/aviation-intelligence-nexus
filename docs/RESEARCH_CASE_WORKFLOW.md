# Persistent local research cases

The opt-in `ResearchCaseService` connects an owner's saved `delay-v2` prediction to a persistent research case, versioned notes and a closing outcome. It is a research record, not an airline incident command, human operational approval or action executor. Every projection retains `operational_approval: false` and `production_ready: false`.

## Enable explicitly in local application code

```python
from services.api.main import create_app
from services.api.research_cases import ResearchCaseService

service = ResearchCaseService(auth_database, separate_case_database)
app = create_app(auth_database, research_cases=service)
```

Both paths are server configuration, never client inputs. The source database must match the app's authenticated database. The separate case database rejects redirects, reuse of the source path/file and existing unversioned tables. Its local schema is version 4; the authenticated application's schema remains 8. On explicit service construction, version 1/2/3 case stores migrate transactionally by adding the missing evidence/agent/gate tables, preserving cases, notes and captured records. Older case code refuses version 4; there is no reverse migration. Retain a verified compatible case-store backup before adopting this increment with important case records. Existing backup tooling does not yet include this sidecar. Normal startup does not instantiate this service. Existing accounts and deployment are unchanged.

The dashboard now includes **Research cases**, beside the historical scenario/history panel. Choose one of your saved prediction IDs and enter a title. The case displays the captured prediction, its server-reported fingerprint and ordered notes. Choose `Closing research outcome` to finish the record; closed cases cannot be edited. Refresh after saving a new prediction or after an uncertain write. Stale versions are rejected; the UI withholds the previous detail until you refresh. Creation retries retain the same key while the page/session and inputs are unchanged. Reloading discards that key, so inspect recent cases before recreating a request after a timeout.

The fixed Node gateway exposes only the fourteen case routes and their allowed methods, rejects query parameters, forwards the existing session/CSRF headers and bounds JSON request bodies to 16 KiB (including multibyte notes). The panel clears private records on sign-out/session change. Viewers see their own case list without creation, edit or attachment controls. Owner authorization remains enforced by the API, regardless of hidden controls.

Normal startup remains disabled for cases. With the service absent, authenticated case endpoints return `503 research_cases_not_configured`; the panel disables writes and explains that the opt-in workspace is needed.

## Start an opt-in native workspace

Do not rebuild the current Docker release for this development step. The factory below requires explicit, matching local state/database paths and refuses container mode. It creates a separate `research-cases.sqlite3` inside that state directory. Choose an existing native research state only after reviewing its migration and backup status; its accounts keep their existing passwords. The following example instead creates a fresh local development workspace with no imported flights, saved predictions or accounts:

```powershell
$env:AIN_STATE_ROOT = Join-Path (Get-Location) '.local/case-workspace'
$env:AIN_DB_PATH = Join-Path $env:AIN_STATE_ROOT 'ain.sqlite3'
$env:PORT = '18110'
$env:AIN_API_PORT = '18111'
$env:AIN_AGENT_JOBS = '0'
.\.venv\Scripts\python.exe -m uvicorn services.api.case_workspace:create_case_app --factory --host 127.0.0.1 --port 18111
```

In another terminal with the same path/port environment settings, run `npm.cmd run dev`. Open `http://127.0.0.1:18110`. A fresh workspace needs its own account created privately with the existing `services.api.manage_users` command. Creating an account does not populate flight data, install models or manufacture a saved prediction. Until an authorized delay-v2 result is saved under that account, the source selector remains empty. Tests seed explicitly synthetic saved results to verify the workflow without claiming model inference. Stop only the development processes in those terminals; the release on 8090 is separate.

Additional focused checks: `python -m unittest tests.test_case_workspace -v` and `node --test tests/test_research_cases.mjs`.

## API workflow

All routes use existing sign-in, Origin and CSRF checks. Writes additionally check the current session role. Records are owner-only, including for administrators; no implicit cross-owner admin access or sharing is added.

| Route | Behavior |
| --- | --- |
| GET `/api/v1/research/case-sources` | Up to 20 owner-saved delay-v2 run IDs and canonical source snapshot hashes. |
| POST `/api/v1/research/cases` | Body: `source_run_id`, `source_sha256`, `title`. Requires UUID `Idempotency-Key` header. Creates one case with an opened event. |
| GET `/api/v1/research/cases` | Up to 20 recent cases belonging to the signed-in user. |
| GET `/api/v1/research/cases/{case_id}` | Case, frozen source snapshot and ordered research history; another owner's ID returns 404. |
| POST `/api/v1/research/cases/{case_id}/events` | Body: `expected_version`, `action` (`note` or `close`), `note`. Appends one version; close records the note as the research outcome. |
| GET `/api/v1/research/case-evidence-sources` | Up to 20 owner-saved knowledge-query IDs, snapshot fingerprints, questions, modes and passage counts. Administrators do not receive other owners' results here. |
| POST `/api/v1/research/cases/{case_id}/evidence` | Body: `expected_version`, `evidence_run_id`, `evidence_sha256`. Captures the owner-saved response and appends an `evidence` event atomically at the next case version. |
| GET `/api/v1/research/cases/{case_id}/evidence/{run_id}` | Owner-only retained response, snapshot fingerprint and attached/current case versions. Does not query the original source or run a model. |
| GET `/api/v1/research/case-agent-sources` | Up to 20 owned reports in `reviewed` or `needs_changes`, with snapshot/report fingerprints and recorded review policy/state. |
| POST `/api/v1/research/cases/{case_id}/agents` | Body: `expected_version`, `agent_run_id`, `agent_sha256`. Captures an owned, reviewed agent record and appends an `agent` event atomically. |
| GET `/api/v1/research/cases/{case_id}/agents/{run_id}` | Owner-only retained report, captured review state and attached/current case versions. Does not execute or restart tools, jobs or models. |
| GET `/api/v1/research/case-gate-sources` | Up to 20 owned, reviewed synthetic proposals, with snapshot/proposal/scenario fingerprints and plan counts. |
| POST `/api/v1/research/cases/{case_id}/gates` | Body: `expected_version`, `gate_run_id`, `gate_sha256`. Captures the saved simulation and review, appending a `gate` event atomically. |
| GET `/api/v1/research/cases/{case_id}/gates/{run_id}` | Owner-only retained synthetic proposal, review and attached/current case versions. Does not solve or apply an allocation. |

Only admin/researcher roles can create/change cases. Viewers can read only records they own, and cannot mutate them. Extra query parameters and extra body authority fields are rejected. Titles are bounded to 160 characters, notes/outcomes to 2,000 characters and histories to 100 versions. Notes are stored as text, not executed.

The source must belong to the requester, identify the same run and declare a research-only delay-v2 result with operational serving unapproved. Its canonical SHA-256 must match the client's observed version. The case captures the exact stored result, not a recomputed prediction or independently authenticated model output. Local filesystem owners can modify the underlying databases; a matched hash is not protected provenance.

Creation replay with the same owner/key/inputs returns the same case ID and its current projection with `replayed: true`; changed inputs conflict. It can replay from the retained case even if the original source history row is gone. Writes use `BEGIN IMMEDIATE`; case changes and their events commit together. Stale/concurrent versions and changes after closure return 409. A failed write is rolled back. After a timeout/conflict, read the current case and reconcile rather than blindly repeating a note.

## Attach saved research evidence

In an open case, choose **My saved evidence**, then **Attach to this case version**. The selector includes only this account's saved Q&A results, including clearly marked abstentions or evidence-only results. Refresh the panel after saving a new Q&A result. It does not manufacture results or fetch an agent report. An attachment captures the canonical saved JSON (at most 64,000 UTF-8 bytes) and its SHA-256; the case projection carries only its reference metadata. Up to ten attachments are permitted, and each saved evidence run can appear only once in a case. The full retained snapshot is fetched separately with **Inspect retained evidence**.

The case must still be open at the observed version, and the current owner-saved response must match the observed fingerprint. A concurrent edit, changed evidence or limit conflict returns 409 without adding an event. Retrying the exact same case/run/fingerprint/expected-version tuple returns its existing attachment and current case with `replayed: true`; it cannot duplicate the attachment. That read-like replay also works after closure or source-history deletion. Changing the tuple conflicts. New attachments to closed cases are rejected. Stored snapshot hashes and evidence-event inventory are checked before projection; corruption withholds the case. The snapshot survives deletion of the original knowledge history row; source deletion is not a retention/deletion policy for captured cases.

This verifies saved-record ownership and consistency. It does not independently authenticate source bytes, revalidate citations against current files, assess semantic entailment, certify answer relevance, prove a model ran or confer operational authority. Filesystem owners can change the stores. The inspector renders the saved response as escaped text, without executing markup or opening arbitrary links. The browser rejects a snapshot for a different case version and requires refresh after uncertain/stale writes.

Focused attachment checks: `python -m unittest tests.test_case_evidence -v` and `node --test tests/test_research_cases.mjs`. Synthetic tests cover forward migration, owner/role boundaries, changed pins, retained snapshots/replay after source deletion, corruption, transactional failure, concurrent expected-version writes, attachment limits, gateway routing and escaped rendering.

## Attach reviewed agent findings

In an open case, choose **My reviewed agent reports**, then **Attach reviewed agent report**. Only records authored by this account and already in `reviewed` or `needs_changes` are eligible. Queued, running, pending-review, cancelled and withdrawn reports cannot be copied. Even administrators cannot attach another owner's report. Temporary access to a pending shared report does not authorize making a retained copy in a case. The attachment does not start an investigation, change its review, extend its sharing or bind a running job/checkpoint to the case.

Up to five reports can be attached per case, each at most 128,000 UTF-8 bytes with at most three saved steps/claims and ten review receipts. The current full saved snapshot must match the observed fingerprint. Its report-content hash is separately recomputed using the existing agent contract (request, steps and claims), and the stored review receipts must reference that hash and agree with the recorded final state. A report requiring a second account must retain a second-account receipt with a reviewer ID different from the case/report author. `standard` review means a second account was not required; it is not a claim that the author personally reviewed it. The UI preserves `needs_changes` rather than presenting every attached report as accepted.

Each report can be attached once per case. Case version changes, changed fingerprints, closed cases and limits reject new writes. Retrying the same case/run/fingerprint/expected-version tuple replays the retained record without duplication, including after source-history deletion or closure. The snapshot and its `agent` event commit together, and their hash/event inventory is checked on reads. Full snapshots are fetched separately; recent case projections contain only link metadata. Captured records survive source deletion, so case retention/deletion and backup policies remain mandatory unfinished work.

**Inspect retained agent report** renders escaped saved JSON with the captured review policy and state. It does not certify tool execution, source authenticity, semantic correctness, reviewer independence or operational approval. Local filesystem owners can change these records; mechanically matching fingerprints are not protected provenance. Source review state is frozen at attachment time, not a current permission or fresh approval. Real-user acceptance remains unverified. Tests use explicitly synthetic accounts and seeded recorded-public-evidence reports without new provider/tool execution.

Focused checks: `python -m unittest tests.test_case_agents -v` and `node --test tests/test_research_cases.mjs`. They exercise owner-only copying, peer/viewer boundaries, excluded pending states, review/report binding, changed pins, corrupted snapshots, idempotent retention, concurrent writes, atomic failure, limits, schema migration, fixed gateway routing and escaped rendering.

## Attach reviewed synthetic gate proposals

In an open case, choose **My reviewed synthetic gate proposals**, then **Attach synthetic gate proposal**. Only owned proposals with a consistent recorded `reviewed` or `needs_changes` decision are eligible. Administrators cannot copy another owner's proposal into their case. Pending or expired unreviewed proposals are excluded. Capturing a saved review is not a new decision and does not open or extend the original review window.

The original `gate-v1` / `scipy-highs-milp` contract independently checks the scenario fingerprint, synthetic scope, candidate/baseline feasibility, objective reconciliation, proposal fingerprint and review-receipt hash/window consistency. Validation uses the recorded review timestamp, so a later wall-clock expiry does not relabel a valid historical decision. This is a consistency check on recorded timestamps, not proof of trusted time, author identity or source authenticity. Source-table scenario/date metadata must also agree with the saved record. Reads and attachments do not call the MILP solver; creating a new proposal remains the separate Gate Allocation Lab workflow.

Up to five proposals can be captured per case, each bounded to 64,000 UTF-8 bytes and the existing maximum of 16 synthetic flights. The full snapshot fingerprint and observed case version must match. Its retained snapshot and `gate` event commit together; changed source pins, stale/closed cases, limits and corruption fail closed. Exact case/run/fingerprint/expected-version retries replay without duplicating the link, including after source deletion or case closure. Source deletion does not delete the captured record; case retention and backup policies remain incomplete. The case projection includes only proposal metadata; the full retained snapshot is fetched separately.

The dashboard labels the proposal **synthetic**, preserves `needs_changes`, compares captured assigned/unassigned counts against the greedy baseline, and provides an escaped snapshot inspector. It does not connect an actual airport schedule, validate representative airline constraints, grant review authority, rerun optimization or apply a gate allocation. Browser role, persistence and responsive checks use a newly computed five-flight synthetic fixture and a synthetic review receipt, not real-user or airline acceptance.

Focused checks: `python -m unittest tests.test_case_gates -v` and `node --test tests/test_research_cases.mjs`. Checks include solver non-execution during attachment/read, owner/role/CSRF boundaries, source and receipt changes, plan/scope validation, expired unreviewed exclusion, retention/replay after source deletion, atomic failure, contention/limits, migration preserving agent/note history, event inventory and fixed gateway routes.

## State, checks and remaining work

Focused check: `python -m unittest tests.test_research_cases -v`. Synthetic fixtures exercise create → note → outcome, re-opened app/service persistence, retained source after deletion, creation replay/conflict, stale/closed writes, concurrent-version contention, role/owner boundaries, CSRF/authentication/body bounds, changed source pin, corrupted snapshot and disabled/misconfigured service behavior. Fixtures are not evidence of real model accuracy or operational decisions. Run `npm test` for regression checks.

The source application database is read for saved predictions and identity; case records/events live only in the configured sidecar. Cross-database authorization/source transactions, protected audit, tenant governance, sharing, retention/deletion policy and independently authenticated provenance are not implemented here. Source deletion does not remove an already captured case snapshot. Existing backup/recovery inventory does **not** include this new case store: it must be integrated before treating case data as release-qualified.

The default deployment is unchanged. The gateway/panel, saved-evidence, reviewed-agent and synthetic gate-proposal attachments, and opt-in native factory are implemented. Case-bound agent execution/checkpoints, representative aviation constraints/limits/load checks, original-user/deployed acceptance and case-store backup/restore qualification remain open. See [remaining phases](REMAINING_DEVELOPMENT.md).
