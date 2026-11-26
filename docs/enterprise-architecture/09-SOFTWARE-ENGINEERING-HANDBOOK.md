# AIN-EA-09 — Software Engineering Handbook

**Project:** Aviation Intelligence Nexus (AIN)  
**Date:** 26 November 2026, Dubai  
**Reviewed revision:** [`1fbc55c`](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/tree/1fbc55c0b70fe5c76e4841e868821dfba922b543)  
**Status:** Consolidated current workflow and proposed engineering practices; no new runtime qualification  
**Change scope:** Documentation only. No code, dependency, credential, data, model, index or deployment changes.

[Project README](../../README.md) · [Implementation baseline](01-CURRENT-IMPLEMENTATION-BASELINE.md) · [Business requirements](02-BUSINESS-REQUIREMENTS-AND-ACCEPTANCE.md) · [Architecture](03-ENTERPRISE-ARCHITECTURE-OVERVIEW.md) · [Security model](08-SECURITY-AND-THREAT-MODEL.md)

## 1. Engineering scope and source of truth

AIN is a local research application with a Node web/proxy layer, FastAPI backend, private SQLite research state, offline ML, optional local Ollama retrieval/agent workflows and bounded operator tooling.

Use source and exact-revision evidence to identify current behavior. Earlier milestone documents may preserve historical counts or limitations; current updates explicitly supersede them. Preserve the 64 original prototype workspaces and distinguish demo data from connected research.

This handbook consolidates existing commands and boundaries, with proposed working conventions clearly identified. It does not certify a fresh clone on every platform or reproduce the private workstation dataset/model. GitHub stores source and reviewed public evidence, not the user's runtime environment.

Repository instructions remain in [AGENTS.md](../../AGENTS.md); detailed daily workflows are in [DEVELOPMENT.md](../DEVELOPMENT.md), [GITHUB_SYNC.md](../GITHUB_SYNC.md) and [DAILY_STARTUP.md](../DAILY_STARTUP.md).

## 2. Toolchain and platform prerequisites

| Requirement | Reviewed baseline | What to verify |
|---|---|---|
| Git | Canonical repository under shah-hussain-bangash | Correct origin, branch and working-tree state before synchronizing. |
| Node/npm | package.json specifies Node >=24 | Use a compatible installed runtime; inspect node --version and npm --version. |
| Python | Existing runbooks/CI test Python 3.14 | Confirm the chosen interpreter and dependency/platform support before creating .venv. |
| Python environment | Project .venv; Windows Scripts/python.exe or POSIX bin/python | npm test uses this environment, not whichever conda/system Python happens to be active. |
| Dependencies | API and infrastructure requirements-lock.txt snapshots | Install both; snapshots lack package hashes and are not supply-chain attestation. |
| Local AI | Optional host Ollama with documented model/index prerequisites | Applicable workflows require trusted compatible weights and private index/model state. |
| Docker | Needed for saved/container release mode, not basic frontend development | Engine access and existing deployment identity are separate from source cloning. |
| Private research state | Import/train/index or trusted restore as appropriate | Never invent accounts or assume a clone includes fitted models, flights or recovery keys. |

The full Windows/Docker/AI setup is not qualified for an older 4GB macOS Monterey laptop merely because Git and VS Code run there. Do not bypass runtime compatibility or recommend a full local model workload without verification. A lightweight client or another supported workstation can be a separate implementation task.

## 3. First-time source setup

### 3.1 Clone once into a new directory

```bash
git clone https://github.com/shah-hussain-bangash/aviation-intelligence-nexus.git
cd aviation-intelligence-nexus
git status --short --branch
node --version
npm --version
```

If a checkout already exists, inspect it rather than cloning over it or deleting local files. Open the repository root in VS Code. The project does not require installing a full application-specific IDE.

### 3.2 Windows Python environment

After confirming that `py -3.14 --version` selects an installed supported interpreter, a fresh Windows setup can use:

```powershell
py -3.14 -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r services/api/requirements-lock.txt -r infra/requirements-lock.txt
& ./.venv/Scripts/python.exe -m pip check
```

This explicit interpreter-selection example requires the Windows Python launcher. If it is absent, choose an existing verified Python 3.14 executable; do not silently create the environment with an unrelated Python version.

Do not overwrite/recreate an existing .venv automatically. Inspect its interpreter and dependency state before modifying it.

### 3.3 POSIX environment

Only on a host with a verified supported Python/runtime and compatible dependencies:

```bash
python3.14 -m venv .venv
./.venv/bin/python -m pip install -r services/api/requirements-lock.txt -r infra/requirements-lock.txt
./.venv/bin/python -m pip check
```

This is an interpreter/path pattern, not a claim that macOS Monterey or every Linux distribution has the required runtime/packages. Windows DPAPI recovery-provider behavior is platform-specific.

### 3.4 Account and optional research prerequisites

For the first Windows local administrator:

```powershell
& ./.venv/Scripts/python.exe -m services.api.manage_users create --username researcher-admin --role admin
```

The tool prompts for a private password. Do not put it in source, arguments, screenshots or chat. No default account/password is supplied. On POSIX, use the corresponding .venv/bin/python executable.

Follow [local identity](../LOCAL_IDENTITY.md) for exact rules. Training, import and index creation are separate governed operations; use [data governance](06-DATA-ARCHITECTURE-AND-GOVERNANCE.md), [model protocol](../DELAY_V2.md) and [knowledge setup](../KNOWLEDGE_STUDIO.md). Do not rerun a consumed holdout experiment just to populate a new machine.

## 4. Choose one startup mode deliberately

| Goal | Command from repository root | Behavior and limitations |
|---|---|---|
| Frontend-only development | npm run dev | Web on loopback 8080 by default; not the full connected backend/model experience. |
| Native API + dashboard | npm run dev:all | Requires project .venv; API 8002 and web 8080 by default; reuses only identified compatible services. |
| Existing saved Docker dashboard | npm start | Validates/reuses or starts the existing qualified API/web pair on 8090; does not build, create accounts/volumes or upgrade to current source. |
| Full source/Node/Python checks | npm test | Requires project environment; no silent backend skip. |
| Local sync eligibility report | npm run sync:plan | Report only; does not commit, push or create a scheduler. |

On Windows, `npm.cmd` can be used where the PowerShell npm script launcher is blocked. Do not weaken system-wide execution policy solely to run the project.

Native launcher Ctrl+C stops services started by that invocation, leaving reused services alone. Successful saved Docker startup can leave services running after the terminal closes. Do not kill unrelated processes by port or delete volumes to bypass a startup refusal.

A fresh Docker build/restore is an explicit release operation described in [LOCAL_DEPLOYMENT_RECOVERY.md](../LOCAL_DEPLOYMENT_RECOVERY.md), not what `npm start` automatically performs.

## 5. Module ownership and change boundaries

| Directory / file | Responsibility | Review focus |
|---|---|---|
| apps/web | Prototype workspaces, connected research panels, browser-local review/export | Scope labels, safe rendering, accessibility, stale input/session behavior |
| scripts | Web hosting/proxy, startup, checks and sync planning | Fixed route/host boundaries, explicit processes and no destructive port cleanup |
| services/api | HTTP/session/role/owner validation, research routes and persistence integration | Typed contracts, current authority, transactions and error projection |
| pipelines | Historical intake/import and provenance/quality | Input bounds, duplicate/conflict semantics, private paths and no arbitrary extraction |
| ml | Offline datasets, protocols, training and diagnostics | Chronological splits, comparators, artifact identity and preserved negative results |
| rag | Corpus/index, retrieval, optional generation and scoped excerpts | Allowlist, model/index compatibility, citations and semantic limits |
| agents | Canonical tools, bounded runtime/jobs, evidence quality and review | Permission/scope, retry identity, bounded effects, cancellation and report authority |
| optimization | Synthetic gate solver and review | Independent feasibility/accounting, bounded inputs and research-only scope |
| infra | Health, readiness, monitoring, recovery, release/rollback tooling | Exact instance/build, private state, no-overwrite and explicit qualification |
| tests | Source, Node, Python and integration fixtures | Independent outcomes and meaningful negative/failure cases |
| docs | Runbooks, experiment reports and architecture | Current vs historical, proposed vs implemented, revision/environment evidence |
| .github/workflows | Hosted validation | Declared dependencies, temporary fixtures, permissions and exact-revision result |

This table is responsibility guidance, not assignment to named team members.

## 6. Proposed coding and API conventions

These conventions guide future changes; they are not a claim that a newly introduced linter/type checker already enforces them.

- Match existing JavaScript ES module and Python module conventions; keep changes scoped and readable.
- Validate untrusted input at the service boundary; reject unsupported fields and out-of-scope dates, identifiers, paths and destinations.
- Keep auth/role/owner checks server-side. Recheck authority at the documented critical transaction/execution boundaries.
- Do not use retrieved/generated content as executable instructions.
- Preserve parameterized SQL and explicit transaction behavior. A retry key must bind to the intended actor/input/effect.
- Treat generated text, imported notes and questions as text; review DOM sinks and response/export allowlists.
- Return stable, sanitized failures without private paths, credentials or provider internals.
- Distinguish missing, rejected, refused, queued, failed and successful outcomes; never substitute fake scores/results.
- Keep model/index/protocol compatibility checks and immutable historical experiment boundaries.
- Add a representative test for a meaningful changed behavior, including relevant negative/race/failure paths. Do not add tests that merely mirror implementation without checking an independent outcome.

Use [architecture decisions](05-ARCHITECTURE-DECISION-RECORDS.md) for consequential boundary changes rather than silently introducing a provider, queue, framework or service.

## 7. Test and verification strategy

### 7.1 Canonical commands

```bash
npm run check
npm run test:web
npm run test:python
npm test
```

`npm test` runs source checks, the configured Node test command and the Python suite. The Python launcher locates .venv itself. Missing environment/dependencies is a failure to resolve, not permission to skip backend verification.

For direct Windows diagnosis:

```powershell
& ./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Use discovery for the complete suite because some older tests import helpers from the tests directory. See [development](../DEVELOPMENT.md) for exact platform/runtime notes.

### 7.2 What checks establish

| Check family | Intended evidence | Cannot establish alone |
|---|---|---|
| Source/repository checks | Defined project structure, selected safety/content constraints and basic consistency | Functional correctness, legal rights or full secret scanning |
| Node tests | Browser/proxy/startup/review/header behavior exercised by configured fixtures | Every browser/device, full visual accessibility or independent security |
| Python tests | Backend/data/model/tool/job/review/recovery behavior using temporary fixtures | Production data quality, host-model semantics or deployed availability |
| Container CI | Build, health/settings/restart checks on empty/synthetic state | Workstation-data restoration, host Ollama quality or production acceptance |
| Browser QA | Specific journeys at recorded viewport/browser and actual/simulated transport scope | Universal UX/accessibility conformance |
| Offline experiments | Frozen dataset/protocol/model comparisons in a specified run | Future-population performance or operational business benefit |
| Operator drills | Exact build/target/state verification under the runbook | Arbitrary-version rollback or disaster recovery on another computer |

Reported old test totals belong to their milestone. Do not hardcode a past count as the permanent definition of done; retain actual passed/failed/skipped results at the intended revision.

### 7.3 CI review

The [Project checks workflow](../../.github/workflows/checks.yml) contains source/Node validation, Python jobs on Linux and Windows with Python 3.14 and dependency consistency checks, plus Linux container smoke/restart verification. Synthetic fixtures do not require private raw data, fitted artifacts or credentials.

After publication, inspect the actual workflow for that commit. A green older revision or local suite is not the new commit's hosted result. Do not claim tests were rerun when only documentation links were checked.

## 8. Git workflow and two-computer collaboration

### 8.1 Inspect before updating an existing checkout

```bash
git remote -v
git branch --show-current
git status --short --branch
git fetch origin
git log --oneline --left-right HEAD...origin/main
```

For a clean manually managed main checkout with no local commits/conflicts and a verified intended upstream, a user may explicitly fast-forward with:

```bash
git pull --ff-only origin main
```

If local changes, staged work, ongoing Git operations or divergent commits exist, inspect and resolve them deliberately. Never discard, force-push, auto-stash or overwrite another computer's work to make synchronization succeed.

### 8.2 Review and publish explicit changes

```bash
git diff
npm run sync:plan
npm test
git add docs/enterprise-architecture/09-SOFTWARE-ENGINEERING-HANDBOOK.md README.md
git diff --cached
git commit -m "docs: maintain engineering handbook"
git push origin main
```

The add command is an example for those reviewed paths, not a command to run when no such local changes exist. Stage only the files actually reviewed. Never indiscriminately stage .env, databases, artifacts or personal files. Verify the remote head and hosted checks after a push.

The existing [daily automated sync policy](../GITHUB_SYNC.md) is stricter than an interactive manual update: it stops on user staging, a non-main branch, conflicts, ahead/diverged remote state or uncertain personal/credential content. It fetches but does not automatically rebase, merge or stash. It requires the project checks before publication.

The schedule mentioned in that historical runbook is configured outside the document. This handbook does not create, inspect or verify an active automation.

### 8.3 Office and home

Commit/push reviewed source at the office; inspect/fetch/update the home checkout before editing. At the end of home work, review/test/commit/push appropriate changes, then update the office checkout. Git does not synchronize Python environments, credentials, raw datasets, fitted models or private runtime databases.

Use a supported machine for full tests and heavy models. Do not assume the old home laptop can run this complete stack; hardware/ESP32 testing and full Aviation research deployment are separate workloads.

## 9. Dependencies, state and secret discipline

[.gitignore](../../.gitignore) excludes private state/environments, archives, keys, logs, databases and many generated formats. Ignoring files is not security review: previously tracked files remain tracked and accidental content can still enter permitted files.

- Review both direct requirements and their resolved dependency changes.
- Preserve compatibility with tested Python/Node and selected container bases.
- Do not represent version pinning as hash verification, SBOM, vulnerability clearance or signed provenance.
- Keep account passwords, tokens, .env, keys, private documents, raw data and model artifacts out of Git/images.
- Review allowed aggregate reports for sensitive questions, notes, paths and identifiers.
- The documented walkthrough MP4 has a specific approved path/blob and size guard; do not bypass source checks to publish arbitrary media.
- If a secret is published, revocation/rotation and authorised history/copy remediation are separate from deleting the current file.

No dependency upgrade, new scan or model-weight download is performed by this handbook.

## 10. Release, schema and recovery discipline

| Change | Required engineering review |
|---|---|
| Source/UI behavior | Relevant tests and meaningful browser QA for UI changes; preserve existing workspaces and scope labels. |
| Schema/state contract | Migration compatibility, old/new state tests, preservation/recovery and release/rollback impact. |
| Model/protocol | New governed experiment where appropriate; freeze evaluation and preserve consumed holdouts/negative results. |
| Corpus/index | Rights/allowlist, compatible model/index identity, source lifecycle and semantic evaluation. |
| Permission/tool | New trust boundary, canonical arguments, denied-access/abuse cases and human authority review. |
| Dependency/runtime | Compatibility, supply-chain review and relevant build/container checks. |
| Local release | Reviewed exact revision, compatible artifacts, trusted backup and existing runbook; source pull does not upgrade saved containers. |
| Recovery/rollback | New/isolated destination, exact target/image/state contract and actual drill outcome; no implicit primary-volume deletion. |

Follow [local deployment/recovery](../LOCAL_DEPLOYMENT_RECOVERY.md), [encrypted recovery](../ENCRYPTED_RECOVERY.md), [isolated rollback](../LOCAL_RELEASE_ROLLBACK.md) and [exact-build rollback evidence](../ROLLBACK_BUILD_EVIDENCE.md). Do not use a past receipt as qualification for a later build.

Managed cloud deployment, independent off-site/key recovery, complete model/prompt rollback and enterprise acceptance remain separate open work.

## 11. Proposed definition of done

For a scoped implementation increment:
1. The problem, user outcome and applicable BR/NFR IDs are clear.
2. The implementation respects scope, contracts, identity and data boundaries.
3. Actual relevant checks pass; failures/skips/unavailable environments are explicit.
4. Changed user journeys have appropriate browser/accessibility evidence.
5. Source, setup instructions, tests, architecture and decision records agree.
6. Reports identify revision/environment and distinguish real, synthetic and recorded data.
7. No secrets/private runtime artifacts are published.
8. Required review occurs and any remaining defects are recorded.
9. The committed source and hosted CI result are verified.
10. No local milestone is mislabelled production-ready or airline-authorised.

For documentation-only changes, verify source-grounded claims, links, IDs and scope; do not invent runtime test outcomes. Existing publication/runbook rules still apply to the actual workflow used. Production acceptance requires the separate P01–P24 process and accountable review.

## 12. Troubleshooting boundaries

| Symptom | Inspect first | Avoid |
|---|---|---|
| .venv missing / wrong Python | Chosen interpreter and both dependency snapshots | Skipping Python tests or installing into an unrelated global/conda environment |
| Port occupied | Service identity and intended native/Docker mode | Killing arbitrary processes or changing ports without checking cookie/origin/configuration |
| Login fails after fresh clone | Actual local account creation and selected private state | Invented default passwords or publishing credentials |
| Predictor/index unavailable | Trusted artifacts, protocol/model/index identities and setup/restore prerequisites | Fake fallback data or automatic held-out experiment reruns |
| npm start refuses deployment | Existing project, container, volume, bind and engine state | Deleting a volume or creating replacement empty state to bypass checks |
| Git push rejected | Local/remote history, branch, staging and origin | Force-push, automatic stash/discard or unreviewed conflict resolution |
| Hosted CI fails | Exact run/job logs and supported platform/dependencies | Quoting an older green run or suppressing a legitimate check |

## 13. Maintenance and next deliverable

Refresh this handbook when commands, dependency support, module boundaries, CI, source-publication policy or release/recovery workflow changes. Keep detailed runbooks authoritative for their scoped operations and record any conflict rather than silently applying unsafe substitutions.

**Verification in this change:** repository source/command definitions and relative links were reviewed. No setup, test suite, browser flow, model call, experiment or deployment was executed for the handbook. No acceptance gate was changed.

**Next planned document:** AIN-EA-10 — Requirements Traceability Matrix, linking business/quality requirements to source, representative tests, evidence and acceptance gaps.
