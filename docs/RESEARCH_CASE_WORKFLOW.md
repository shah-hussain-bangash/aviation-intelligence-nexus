# Persistent local research cases

The opt-in `ResearchCaseService` connects an owner's saved `delay-v2` prediction to a persistent research case, versioned notes and a closing outcome. It is a research record, not an airline incident command, human operational approval or action executor. Every projection retains `operational_approval: false` and `production_ready: false`.

## Enable explicitly in local application code

```python
from services.api.main import create_app
from services.api.research_cases import ResearchCaseService

service = ResearchCaseService(auth_database, separate_case_database)
app = create_app(auth_database, research_cases=service)
```

Both paths are server configuration, never client inputs. The source database must match the app's authenticated database. The separate case database rejects redirects, reuse of the source path/file and existing unversioned tables. Its local schema is version 1; the authenticated application's schema remains 8. Normal startup does not instantiate this service. Existing accounts, deployment and backups are unchanged.

The dashboard now includes **Research cases**, beside the historical scenario/history panel. Choose one of your saved prediction IDs and enter a title. The case displays the captured prediction, its server-reported fingerprint and ordered notes. Choose `Closing research outcome` to finish the record; closed cases cannot be edited. Refresh after saving a new prediction or after an uncertain write. Stale versions are rejected; the UI withholds the previous detail until you refresh. Creation retries retain the same key while the page/session and inputs are unchanged. Reloading discards that key, so inspect recent cases before recreating a request after a timeout.

The fixed Node gateway exposes only the five case routes and their allowed methods, rejects query parameters, forwards the existing session/CSRF headers and bounds JSON request bodies to 16 KiB (including multibyte notes). The panel clears private records on sign-out/session change. Viewers see their own case list without creation or edit controls. Owner authorization remains enforced by the API, regardless of hidden controls.

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

Only admin/researcher roles can create/change cases. Viewers can read only records they own, and cannot mutate them. Extra query parameters and extra body authority fields are rejected. Titles are bounded to 160 characters, notes/outcomes to 2,000 characters and histories to 100 versions. Notes are stored as text, not executed.

The source must belong to the requester, identify the same run and declare a research-only delay-v2 result with operational serving unapproved. Its canonical SHA-256 must match the client's observed version. The case captures the exact stored result, not a recomputed prediction or independently authenticated model output. Local filesystem owners can modify the underlying databases; a matched hash is not protected provenance.

Creation replay with the same owner/key/inputs returns the same case ID and its current projection with `replayed: true`; changed inputs conflict. It can replay from the retained case even if the original source history row is gone. Writes use `BEGIN IMMEDIATE`; case changes and their events commit together. Stale/concurrent versions and changes after closure return 409. A failed write is rolled back. After a timeout/conflict, read the current case and reconcile rather than blindly repeating a note.

## State, checks and remaining work

Focused check: `python -m unittest tests.test_research_cases -v`. Synthetic fixtures exercise create → note → outcome, re-opened app/service persistence, retained source after deletion, creation replay/conflict, stale/closed writes, concurrent-version contention, role/owner boundaries, CSRF/authentication/body bounds, changed source pin, corrupted snapshot and disabled/misconfigured service behavior. Fixtures are not evidence of real model accuracy or operational decisions. Run `npm test` for regression checks.

The source application database is read for saved predictions and identity; case records/events live only in the configured sidecar. Cross-database authorization/source transactions, protected audit, tenant governance, sharing, retention/deletion policy and independently authenticated provenance are not implemented here. Source deletion does not remove an already captured case snapshot. Existing backup/recovery inventory does **not** include this new case store: it must be integrated before treating case data as release-qualified.

The default deployment is unchanged. The gateway/panel and opt-in native factory are implemented. Evidence/agent/optimization attachments, representative limits/load checks, original-user/deployed acceptance and case-store backup/restore qualification remain open. See [remaining phases](REMAINING_DEVELOPMENT.md).
