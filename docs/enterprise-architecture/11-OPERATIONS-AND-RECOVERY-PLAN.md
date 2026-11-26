# Operations and Recovery Plan

**Document:** AIN-EA-11  
**Project:** Aviation Intelligence Nexus  
**Reviewed:** 26 November 2026  
**Source baseline:** `8cf46602e3a51f314b92afc142ef5376fac8c264`  
**Status:** Operator guide for the existing local research deployment; proposed enterprise responsibilities and targets remain unapproved.

## 1. Purpose and authority

Operate the saved research dashboard, distinguish application failures from unavailable dependencies, preserve private state, and recover through a verified fresh destination. This document consolidates the sequence of decisions; the linked detailed runbooks remain authoritative for commands and prerequisites. It does not install a supervisor, create a backup schedule, deploy a release or execute a recovery drill.

The application supports research on historical aviation data and synthetic proposals. Its 64 workspaces are not 64 independently implemented production services. All 24 production requirements remain open. Read the [implementation baseline](01-CURRENT-IMPLEMENTATION-BASELINE.md), [requirements](02-BUSINESS-REQUIREMENTS-AND-ACCEPTANCE.md), [security model](08-SECURITY-AND-THREAT-MODEL.md), and [traceability matrix](10-REQUIREMENTS-TRACEABILITY-MATRIX.md) alongside this plan.

## 2. Identify the instance before acting

| Mode | Entry point | State and operating boundary |
| --- | --- | --- |
| Frontend development | `npm run dev`; loopback port 8080 | UI development alone does not establish backend readiness. |
| Connected native development | `npm run dev:all`; web 8080 and API 8002 | Uses the selected native private state. Stop owned launcher children with Ctrl+C; do not terminate unidentified port occupants. |
| Saved Docker dashboard | `npm.cmd start` on Windows; dashboard 8090 | Existing `ain-local-release` project and `ain-local-release_state` volume. API state is under `/app/.local/active`. |
| Isolated rollback drill | Detailed rollback controller; dashboard 8091 | Fixed `ain-rollback-drill` project and its own state volume. Never substitute the primary volume. |
| Observer outage drill | Approved isolated endpoint port 8092 | Separate observer history directory; do not mix its history with primary port 8090. |

A source checkout, a running image, a native state directory and a Docker named volume are different assets. Git clone retrieves committed source, not saved accounts, session state, historical database, fitted artifacts or host Ollama weights. A successful pull does not upgrade existing containers.

**Before a mutation, record privately:** intended project/port; current source and running image identities; exact state location; active users/jobs; selected trusted snapshot; available disk space; and the command's target. Do not put passwords, cookies, raw data, full private paths or account fingerprints into public issues.

See [engineering workflow](09-SOFTWARE-ENGINEERING-HANDBOOK.md), [development instructions](../DEVELOPMENT.md), and [daily startup](../DAILY_STARTUP.md).

## 3. Daily operation

### 3.1 Start the saved dashboard

1. Open the correct checkout and start Docker Desktop's engine.
2. On Windows run `npm.cmd start`, or select **AIN: Start saved Docker dashboard** in VS Code.
3. Wait for the launcher's explicit readiness result; open `http://127.0.0.1:8090`.
4. Sign in with an existing local account. Inspect the authenticated **Know what is running** panel when investigating identity/artifact questions.
5. Use a representative authorized research journey before treating that capability as available.

The launcher reuses an already identified, ready dashboard without Docker changes. Otherwise it checks the existing project, services, named volume, state path and loopback binding before starting the existing pair. It refuses unknown port occupants and unexpected deployments.

It does not build/pull images, initialize replacement containers, create accounts, change passwords, upgrade source or recover data. Missing state is an investigation, not permission to create an empty replacement. Closing a successful startup terminal leaves Docker services running. See [launcher behavior and failure messages](../DAILY_STARTUP.md) and [launcher source](../../scripts/start-release.mjs).

### 3.2 During work and shutdown

- Confirm research outputs show the expected historical context and scope. A healthy HTTP response does not approve an AI answer.
- Review queue progress before planned interruption. Long-running model calls are bounded by their own controls; cooperative cancellation is not an instantaneous kill.
- Save required research records through supported application flows. Do not copy a live SQLite file as an assumed consistent backup.
- For native development, stop the launcher with Ctrl+C. For Docker, stop only the identified services deliberately and preserve their named volume.
- Manage the observer separately. Stopping the application and stopping its observer are different actions; an observer can legitimately record application unavailability during maintenance.

Refer to [agent operations](../AGENT_OPERATIONS.md) and [deployment and recovery](../LOCAL_DEPLOYMENT_RECOVERY.md). This plan does not introduce unattended shutdown, backup or restart automation.

## 4. Monitoring and interpretation

| Signal | What it establishes | What it does not establish |
| --- | --- | --- |
| Frontend `/__ain/health` | Expected frontend liveness | Database, model or user-journey success |
| Frontend `/__ain/ready` | Database-backed API readiness through the web service | Every tool, local AI model or business acceptance criterion |
| Administrator **See what needs attention** | Enabled component samples: schema query, v2 artifact checksum and configured Ollama model availability | Semantic AI quality, database corruption scan or service-level objective |
| Request counters and rolling p95 | Bounded completed API responses measured by middleware | Browser latency, an all-time history or semantic failures inside HTTP 200 |
| Separate observer fresh status | Recent observations of frontend liveness and backend readiness | Off-host monitoring, task supervision proof or continuous coverage |
| Observer incident history | Bounded recorded unavailable/recovered endpoint transitions | Current health, protected audit or exact actual outage duration |
| Restore/rollback receipt | Dated scoped operation evidence with its recorded identity | Current backup freshness or compatibility of every later build |

With component monitoring enabled, sampling runs at startup and 30 seconds after the preceding sample completes. Samples older than 90 seconds become unknown. Browser monitoring refreshes every 30 seconds while an administrator is signed in; refresh failure clears the previous display. Process counters and transitions reset after API restart. Snapshot persistence failure is a visible fault.

The separate observer polls every five seconds. Its current health expires at 15 seconds; missing, malformed or future-dated samples are unknown. Its persistent history retains the latest 100 events with observed/rolled-out counts. A corrupt history or backward clock stops the writer for private investigation. Do not repair an incident by silently deleting its history.

Sources: [component monitoring](../LOCAL_MONITORING.md), [monitoring integrity](../MONITORING_INTEGRITY.md), [observer operation](../LOCAL_OBSERVER.md), and [observer implementation](../../infra/local_observer.py).

### 4.1 Inspect the observer

From the matching project Python environment:

```powershell
python -m infra.local_observer status --directory .local/observer
python -m infra.local_observer history --directory .local/observer
```

These commands inspect existing records; they do not install a scheduled task or repair the application. The Windows management runbook provides explicit Install, Status, Stop and Start actions. Source availability alone does not establish that a task is installed.

The configured periodic recovery trigger offers another launch opportunity after an exited process; it does not repair a hung process or establish a guaranteed recovery time. The observer cannot independently monitor its own powered-off workstation. The Docker dashboard only receives observer observations when its reviewed read-only overlay is present. Follow [the observer runbook](../LOCAL_OBSERVER.md); do not recreate containers merely to resolve an unknown badge.

## 5. Incident response

The following levels and responsibilities are **proposed operating conventions**, not an existing staffed on-call service. No acknowledgement deadlines or escalation contacts have been agreed.

| Level | Examples | Initial response |
| --- | --- | --- |
| Critical integrity/security concern | Unexpected state identity, suspected credential exposure, corrupted snapshot, unauthorized access | Stop the affected workflow; preserve trusted evidence and state; restrict the affected access through supported controls. Do not publish secrets or attempt a blind restore. |
| Research service unavailable | Readiness failure, unavailable database/model, failed container health | Identify the instance and dependency; inspect bounded local status/logs; use the matching runbook. |
| Degraded or uncertain evidence | Stale observer, missing component sample, AI refusal, incomplete result | Label the result unknown/incomplete; investigate that specific signal; retain the limitation. |

### 5.1 Response sequence

1. **Observe:** capture time, project/port, source/image identity, symptom and freshness of the signal.
2. **Classify:** distinguish frontend, API/database, artifact, Ollama, queue, observer and security failures.
3. **Contain:** pause affected use where necessary; preserve the current state and trusted backups. Do not delete volumes, overwrite keys or kill unrelated services.
4. **Diagnose:** use the decision table below and detailed runbook. Sanitize shared evidence; application/server logs have separate privacy properties from the bounded monitor.
5. **Recover:** choose ordinary service startup, dependency repair, isolated restore or compatible isolated rollback. These are different procedures.
6. **Validate:** check identity, fresh readiness and the affected authenticated journey. A healthy badge alone is insufficient.
7. **Record:** document impact, evidence, change, validation and remaining uncertainty. Close only the observed incident; do not claim universal recovery.

| Symptom | Investigation and action | Required exit evidence |
| --- | --- | --- |
| Docker engine unavailable | Start Docker Desktop; wait for the engine; retry saved startup. | Launcher verifies the intended dashboard and backend. |
| Port 8090 is occupied unexpectedly | Identify its owner; launcher must refuse replacement. | Correct service identity established without killing an unrelated process. |
| Frontend live but readiness fails | Inspect the intended API health/logs and database accessibility; use deployment runbook. | Fresh readiness plus an authorized database-backed action. |
| Model checksum mismatch | Pause affected predictions; inspect approved artifact/report identity. Do not edit a checksum to hide mismatch. | Trusted matching artifact and a known research prediction check. |
| Ollama unavailable or model missing | Inspect host service and configured model availability; preserve database state. | Required models available and the affected bounded retrieval/agent journey checked. |
| Waiting/running investigation appears stuck | Inspect queue and worker observations; use supported cancellation/restart behavior. Avoid duplicate submissions. | Correct terminal/restart state and a controlled new investigation, where appropriate. |
| Observer unknown but dashboard works | Check freshness, process/task state and record persistence separately. | New valid observation; coverage gap retained honestly. |
| Restore or rollback fails | Keep the primary instance intact; preserve failure evidence and isolated target. Investigate before retry. | Matching scoped verification succeeds, or incident remains open. |

No local monitor sends external email, Slack or SMS alerts. Proposed incident and security owners must be assigned before any staffed-service claim. See [security response boundaries](08-SECURITY-AND-THREAT-MODEL.md).

## 6. Backup policy and snapshot procedure

### 6.1 Current capability versus proposed policy

The repository implements operator-driven snapshots and verification. It does not establish a scheduled backup service, retention rotation, independent key recovery or off-site protection.

**RPO and RTO are not agreed.** RPO needs an accepted maximum data-loss interval and proven backup frequency. RTO needs a measured complete recovery journey, including infrastructure, dependencies, authentication and user acceptance. Historical file-copy/validation timings exclude parts of that journey and must not be relabeled as these objectives.

Before an enterprise rollout, an accountable owner must set frequency, retention, storage access, independent copy/key recovery, capacity and drill frequency. These are proposed acceptance decisions, not claims that an operator already performs them.

### 6.2 Select and verify the correct snapshot

Use [the recovery runbook](../LOCAL_DEPLOYMENT_RECOVERY.md) for exact commands and instance-specific source paths.

1. Identify the actual state source. The runbook's native `.local` example is not automatically the active Docker state.
2. Keep source/dependency identities and sufficient disk space available.
3. Avoid replacing the active model or index while capturing the snapshot.
4. Create a new destination; existing outputs are refused.
5. Run snapshot verification and retain its private manifest.
6. Plan a separate restore drill. A verified manifest alone does not demonstrate restored application operation.

SQLite's online backup captures committed database state. The snapshot includes the database and selected active model/report/index artifacts with hashes, sizes, schema and row-count checks. It is not an atomic transaction spanning all application files.

Raw downloads, training datasets, retired artifacts and host Ollama weights are excluded. Derived monitor snapshots are not the recovery snapshot. Keep a separate dependency/source-reconstruction plan for excluded assets.

### 6.3 Encryption and keys

The separate [encrypted recovery procedure](../ENCRYPTED_RECOVERY.md) seals a verified snapshot and authenticates ciphertext before archive parsing/restoration. Its Windows DPAPI key is outside the checkout and tied to the normal user's profile/computer. Do not replace a key to resolve an error.

This does not provide portable recovery after loss of that profile/computer. Plaintext source snapshots remain; crash cleanup and secure erasure are not guaranteed. Keep both snapshots and keys private and out of Git. Only restore trusted model artifacts: checksum verification does not make malicious serialized content safe.

## 7. Restore and return to service

Follow [local deployment recovery](../LOCAL_DEPLOYMENT_RECOVERY.md) and, for sealed copies, [encrypted recovery](../ENCRYPTED_RECOVERY.md). Restoration must target a **new private directory or fresh explicitly identified drill volume**. An existing destination is refused; do not delete it to bypass the guard.

| Stage | Required check |
| --- | --- |
| Preflight | Trusted snapshot; matching source/dependencies; correct destination; free disk; original instance preserved |
| Snapshot | Manifest, schema, integrity, hashes and expected row counts verified |
| Identity | Intended image/source revision, port, state mount and isolation verified |
| Accounts | Account records retained; restored sessions revoked; authorized user signs in again |
| Artifacts | Active model/report and document index match the snapshot |
| Functional | Known historical prediction; scoped retrieval; bounded agent scenario where dependencies are available |
| Queue | Interrupted work handled according to restoration behavior; no silent replay assumed |
| Handoff | Operator records exact checks, failures, missing dependencies and accepted scope |

Use `infra.validate_restored_state` and `infra.verify_deployment` as directed by the runbook. A restored account is not a restored session. A local smoke run is not authenticated business acceptance.

Previously recorded recovery includes 2,835,101 historical rows and selected model/retrieval/agent checks. That is dated workstation evidence. This document performs no new restore and does not establish recovery on the user's older Mac or after workstation/key loss.

## 8. Release changes and rollback

Daily saved startup is not a release upgrade. Before a release, review committed source, intended image identities, tests, state contracts, active jobs and a trusted backup. Follow the [engineering handbook](09-SOFTWARE-ENGINEERING-HANDBOOK.md) and [release readiness runbook](../RELEASE_READINESS.md).

Existing rollback capability is an **isolated application drill**, not automatic primary-deployment rollback. The controller:

- Targets only `ain-rollback-drill` on 8091 and its own named volume.
- Requires locally retained immutable image IDs and matching source labels.
- Refuses schema or selected state-contract mismatches and active waiting/running work.
- Switches candidate → prior → candidate while retaining the isolated data volume.
- Verifies selected rows, account fingerprints, artifacts and an exact historical prediction.
- Attempts candidate recovery after a target failure; that recovery can itself fail.

The web service stops during switching. The worker is disabled in the isolated drill. It does not downgrade a database, roll back model/prompt changes, qualify arbitrary image pairs or establish zero downtime.

Use [isolated rollback instructions](../LOCAL_RELEASE_ROLLBACK.md) and [build-bound evidence rules](../ROLLBACK_BUILD_EVIDENCE.md). A historical receipt does not qualify a later running candidate. Leave the main project outside drill mutation scope.

## 9. Two-computer and dependency continuity

The office Windows workstation and home computer can share committed source through Git. They have separate accounts, local databases, containers, credentials and model availability unless explicitly provisioned through supported processes.

- Use the [Git sync procedure](../GITHUB_SYNC.md); preserve local edits and stop on conflicts.
- Verify supported Python/Node/runtime dependencies on each computer using [development instructions](../DEVELOPMENT.md).
- Do not expect the home computer to open a Windows DPAPI key.
- Rebuild/re-provision supported services explicitly; do not assume a cloned repository carries the saved office dashboard.
- Treat constrained-memory full-stack operation and independent-host recovery as unqualified until measured on that machine.

No live airline connection, remote office endpoint or cross-computer automatic state synchronization is created by this plan.

## 10. Proposed accountability and acceptance evidence

| Responsibility | Assignment required | Evidence needed before claiming completion |
| --- | --- | --- |
| Local service operator | Named person and maintenance authority | Instance inventory, successful startup and affected-journey check |
| Data/recovery owner | Named owner and agreed RPO/retention | Correct-source snapshot, independent copy policy and accepted restore drill |
| Security/key custodian | Named owner and recovery authority | Private access controls, independent key-recovery decision and exercised procedure |
| Release owner | Named reviewer and change authority | Exact source/image pair, relevant checks, state compatibility and scoped receipt |
| Research reviewer | Named person with decision scope | Semantic assessment of outputs; limitations and historical/synthetic context retained |
| Incident escalation | Named contact and agreed response expectations | Alert delivery, acknowledgement and escalation exercise |

These assignments are pending; role labels do not imply staffed teams or operational approval. Relevant requirements are BR-14, BR-16, BR-17 and BR-18, plus quality requirements for security, integrity, reliability and maintainability. Use the [traceability matrix](10-REQUIREMENTS-TRACEABILITY-MATRIX.md) for full mappings.

## 11. Verification register for this document

| Area | Existing verification source | Interpretation |
| --- | --- | --- |
| Saved startup refusal/reuse | [Node startup tests](../../tests/test_startup.mjs) | Synthetic branches and recorded real already-running scope are distinguished in daily startup. |
| Monitoring | [Monitoring tests](../../tests/test_monitoring.py), [integrity tests](../../tests/test_monitoring_integrity.py) | Bounded observations and stale/error behavior; not external alerting. |
| Observer | [Observer tests](../../tests/test_local_observer.py), [history tests](../../tests/test_observer_history.py) | Local probe/history behavior; not independent uptime. |
| Snapshot and restore | [Recovery tests](../../tests/test_recovery.py), [recorded deployment recovery](../reports/Local_Deployment_Recovery.json) | Selected implementation and historical workstation drill evidence. |
| Encryption | [Sealed recovery tests](../../tests/test_sealed_recovery.py), [recorded encrypted drill](../reports/Encrypted_Recovery.json) | Local encryption/recovery scope; no independent key recovery. |
| Rollback | [Controller tests](../../tests/test_releases.py), [binding tests](../../tests/test_rollback_binding.py), [recorded drill](../reports/Local_Release_Rollback.json) | Conservative isolated pair checks; no primary rollback approval. |

Preparation consisted of reviewing the linked runbooks at the source baseline and checking repository link targets. No application changes, runtime checks, disruptive drills, scheduled tasks or backups were executed for this documentation change. Historical reports retain their own dates and scope.

The final package document is **AIN-EA-12: Readiness and Evidence Register**, which will consolidate open gates, evidence freshness, ownership and acceptance decisions.
