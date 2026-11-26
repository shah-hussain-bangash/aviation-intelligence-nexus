# AIN-EA-02 — Business Requirements and Acceptance Criteria

**Project:** Aviation Intelligence Nexus (AIN)  
**Date:** 26 November 2026, Dubai  
**Status:** Proposed requirements baseline for owner review; no stakeholder or production sign-off asserted  
**Reviewed repository revision:** [`9f8f1e4`](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/tree/9f8f1e4a4e18c3feea343b52e4d3f3e144a6d4d4)  
**Predecessor:** [AIN-EA-01 — Current Implementation Baseline](01-CURRENT-IMPLEMENTATION-BASELINE.md)  
**Change scope:** Documentation only. Existing application behavior, experiment protocols and production gates remain unchanged.

[Project README](../../README.md) · [Implementation history](../PROJECT_STATUS.md) · [Production readiness catalog](../../infra/readiness.json)

## 1. Business problem and intended outcome

An aviation research analyst needs to distinguish historical evidence, experimental model output and synthetic operational scenarios. A polished dashboard alone cannot establish whether a figure comes from an imported dataset, a frozen evaluation, an active local model or a demonstration fixture.

AIN's immediate business objective is a reproducible **research decision-support workflow**: inspect provenance, compare a model against a baseline, investigate evidence and retain a clearly bounded research review. It is not an airline control system or a currently accepted commercial airline platform.

The proposed outcomes are:

| Objective | Required outcome | Evidence of success |
|---|---|---|
| O01 — Evidence clarity | Analysts can identify data period, source, scope and limitations before interpreting results. | Reconciled source manifests, visible provenance and a recorded analyst walkthrough. |
| O02 — Reproducible model research | Model selection and test evaluation remain traceable to a fixed protocol and temporal split. | Dataset/model/report identities, retained comparisons and no post-holdout tuning represented as independent evidence. |
| O03 — Bounded investigation | Local AI can assist research within explicit tool and document permissions. | Exact evidence quotations, scope/permission denials, retained failures and a reviewer decision. |
| O04 — Accountable simulation | Gate proposals can be checked and reviewed without issuing airport actions. | Feasibility/accounting checks, synthetic labels and proposal-bound review records. |
| O05 — Repeatable engineering | A new authorized operator can start an appropriate instance, verify its state and follow recovery instructions. | Versioned setup records, exact-build checks and a scoped operator drill. |

No time saving, airline cost reduction, revenue lift, safety improvement or user-adoption target has been measured or agreed. Such targets require an owner, baseline population, measurement method and pilot before being claimed.

## 2. Stakeholders, roles and decisions

These are **proposed responsibilities**, not named or appointed individuals. Application roles are distinct from business accountability.

| Stakeholder / role | Decisions and responsibilities | Boundary |
|---|---|---|
| Project/product owner | Approve scope, exclusions, priority and research acceptance criteria. | No owner signature or airline mandate is recorded here. |
| Research analyst | Inspect data, run permitted historical scenarios and evaluate evidence. | Research results cannot authorize airline action. |
| Research reviewer / domain specialist | Challenge relevance, assumptions, limitations and conclusions. | A different login is not proof of a different person or independent authority. |
| Data steward | Review provenance, terms, purpose, retention and allowed publication. | Historical public-data access does not approve unrelated operational use. |
| Software / AI engineer | Implement contracts, preserve experiment boundaries, reproduce tests and investigate failures. | Test success is not a business or production sign-off. |
| Local administrator / operator | Provision accounts, manage trusted artifacts and perform approved local maintenance. | Local admin privileges are not tenant-grade enterprise identity governance. |
| Security / operations reviewer | Define and review deployment security, recovery and service objectives. | Production assurance is pending an identified environment and accountable owner. |

Current application roles are `viewer`, `researcher` and `admin`. Read access does not confer permission to calculate scenarios, invoke tools, see other owners' records or approve operations. Use the current [local role matrix](../LOCAL_IDENTITY.md) and server-side tests as the implementation reference.

## 3. Scope and delivery boundaries

### 3.1 In scope for the current research milestone

- Historical US BTS January–May 2025 ingestion, recorded data-quality evidence and bounded aggregate queries.
- Delay-15 model reports and restricted historical-scenario inference.
- Recorded duration-regression, threshold, distribution and route diagnostics, retaining negative findings.
- Synthetic gate optimization, feasibility checks and research decisions.
- Allowlisted project-document retrieval, optional local generation, bounded investigation tools and research review.
- Local account/session controls, histories, jobs, monitoring, operator recovery and isolated rollback mechanisms.
- Existing demonstration workspaces with truthful labels.

### 3.2 Explicitly excluded from current acceptance

- Live UAE airline feeds, real airport stand allocation and operational flight dispatch.
- Ticketing, fare/revenue optimisation, passenger identity processing or payment effects.
- Arbitrary model uploads, unrestricted SQL/shell/tool calls or arbitrary document-source access.
- Enterprise SSO/MFA, commercial multi-tenancy, cloud service-level commitments or independently qualified production security.
- Autonomous airline actions, operational reviewer authority or certification.
- A claim that all 64 demonstration workspaces are complete backend services.

The broader portfolio vision may cover flight operations, revenue, maintenance, airport operations and customer experience. Those domains are **future scope unless separately evidenced and accepted**. They do not enter this release simply because a workspace or architecture diagram names them.

## 4. Acceptance model and evidence rules

The requirement IDs below are new business identifiers (`AIN-BR-xx` and `AIN-NFR-xx`). They do not replace the existing P01–P24 readiness IDs.

- **Must** means required for the proposed research milestone's stated use; it does not imply the present implementation already satisfies the whole requirement.
- **Should** means valuable but deferrable through an explicit owner-reviewed decision.
- **Existing local implementation** identifies a baseline capability, not a new test or accepted release.
- **Partial / experimental** identifies working portions with substantive quality or delivery limits.
- Every requirement's **new owner-reviewed acceptance is pending** until the actual exercise and review are recorded.

An acceptance record must contain requirement/test ID, exact source revision, environment/dependency versions, fixture or authorized dataset identity, steps, observed outcome, sanitized evidence path/hash, known defects and reviewer/date. Distinguish a current execution from a historical receipt. Never create a passing record merely to satisfy a checklist.

## 5. Functional business requirements

| ID / priority | Requirement and business reason | Measurable acceptance criteria | Existing evidence / current boundary |
|---|---|---|---|
| AIN-BR-01 / Must | Distinguish demonstration workspaces from connected research services. | In the scope walkthrough, each selected panel identifies historical, simulated, recorded-report or active-inference origin. Preserve the 64-workspace navigation. No selected demo panel is described as a live operational service. | B01 in [baseline](01-CURRENT-IMPLEMENTATION-BASELINE.md); [dashboard tests](../../tests/test_dashboard.mjs). Existing mixed-scope UI; walkthrough acceptance pending. |
| AIN-BR-02 / Must | Require authenticated, role-scoped research access. | Anonymous protected requests are denied; viewers cannot invoke researcher-only calculations; disabled/revoked accounts lose access; owner-scoped records cannot be read by another ordinary account. Record expected HTTP outcomes for each case. | [Identity](../LOCAL_IDENTITY.md), [auth tests](../../tests/test_auth.py), [account tests](../../tests/test_account_security.py). Local identity implemented; enterprise identity excluded. |
| AIN-BR-03 / Must | Preserve import provenance and avoid duplicate historical ingestion. | In a temporary test database, import a permitted fixture, reconcile accepted/excluded rows and its source identity, then repeat the same import without duplicated flight rows. A malformed fixture has an explicit rejected/quarantined outcome under the chosen intake path. | [Ingestion](../DATA_INGESTION.md), [local intake](../LOCAL_DATA_INTAKE.md), [tests](../../tests/test_ingestion.py). Historical import exists; scheduled operational ingestion is not accepted. |
| AIN-BR-04 / Must | Make data-quality and lineage evidence understandable. | The displayed recorded audit matches its pinned report's period and counts. Tampered/unavailable evidence is not displayed as valid. Clearly state that refreshing the panel does not rerun a source audit. | [Lineage](../DATA_QUALITY_LINEAGE.md), [tests](../../tests/test_data_quality.py). Structural audit does not prove source truth or global row equality. |
| AIN-BR-05 / Must | Preserve temporal ML evaluation and baseline comparisons. | Verify the recorded protocol, training/validation/test periods and reported comparator metrics; changed protocol/artifact identities fail the relevant checks. Retain failed experiments. No retuning on May test outcomes is presented as an independent test. | [v2 protocol/results](../DELAY_V2.md), [v2 tests](../../tests/test_v2.py), [duration negative result](../DELAY_DURATION_REGRESSION.md). Research-only model gate. |
| AIN-BR-06 / Must | Return bounded historical research predictions with context. | A supported scenario returns a bounded probability plus model identity and historical scope. Unsupported date/vocabulary/extra-field input is rejected. A missing or mismatched model is unavailable, never silently replaced by a fake probability. | [Prediction contract](../RESEARCH_PREDICTION.md), [prediction tests](../../tests/test_prediction.py). No operational forecast or cancellation-risk claim. |
| AIN-BR-07 / Should | Help analysts inspect trade-offs, distributions and route history. | A recorded diagnostic panel reconciles counts with its source report. A route query echoes the selected direction/period; missing/sparse data and busy/failure cases are explicit. Export contains only allowed aggregate evidence. | [Trade-offs](../MODEL_DECISION_TRADEOFFS.md), [route lookup](../HISTORICAL_ROUTE_LOOKUP.md), [route tests](../../tests/test_route_history.py). Retrospective evidence, not causality or future performance. |
| AIN-BR-08 / Must | Produce feasible synthetic gate proposals with a transparent baseline. | Run the defined synthetic cases; independently check assignments, compatibility, overlap and cost/objective accounting. Reject malformed/unverifiable candidates. Time-limited feasibility is not labelled proven optimality. Display the synthetic label on result and export. | [Gate lab](../GATE_OPTIMIZATION.md), [solver tests](../../tests/test_gates.py). No real airport constraints or actions. |
| AIN-BR-09 / Must | Bind a gate research decision to the exact saved proposal. | Accept an intact supported proposal inside its original 24-hour window. Reject changed, expired or conflicting submissions; identical valid retry does not create a different decision. Legacy proposals stay readable without fabricated new review eligibility. | [Gate review](../GATE_PROPOSAL_REVIEW.md), [review tests](../../tests/test_gate_review.py). Self-review remains allowed for this synthetic workflow; no independent operational approval. |
| AIN-BR-10 / Must | Retrieve authorised project evidence with traceable citations. | The test corpus stays within the approved allowlist; citations resolve to the recorded source revision and excerpt. Unknown/corrupt index or model failures produce explicit unavailability. Retrieved text cannot become a tool instruction. | [Knowledge studio](../KNOWLEDGE_STUDIO.md), [knowledge tests](../../tests/test_knowledge.py). Citation validity alone does not establish relevance or answer quality. |
| AIN-BR-11 / Must | Keep the Scoped Answer Lab's research and uncertainty boundaries visible. | Preserve explicit experiment selection and acknowledgment. Exercise valid excerpt, conflict clarification, coverage refusal, known paraphrase refusal and unavailable-generation cases. Input/account changes invalidate pending display/export state. | [Scoped lab](../SCOPED_ANSWER_LAB.md), [lab tests](../../tests/test_scoped_lab.py). Semantic suitability remains experimental; no new quality threshold is invented. |
| AIN-BR-12 / Should | Allow transparent self-review and local artifact inspection. | Export a result-bound draft/assessment; reopen a valid bounded UTF-8 file without an upload or model call. Reject altered/oversized/invalid files. Label imported artifacts unsigned and keep them separate from live results. | [Self-review](../SCOPED_SELF_REVIEW.md), [inspector](../REVIEW_FILE_INSPECTOR.md), [tests](../../tests/test_scoped_review.mjs). Content consistency, not verified authorship or semantic acceptance. |
| AIN-BR-13 / Must | Restrict agent execution to permitted research tools. | Unauthorised tools, noncanonical arguments or forbidden source scope are denied. Retain evidence and identified mechanical gaps. Require review rather than treating generated prose as an operational decision. | [Investigation agent](../INVESTIGATION_AGENT.md), [quality](../AGENT_REPORT_QUALITY.md), [agent tests](../../tests/test_agent.py). Bounded single-agent local research, not general autonomous airline operations. |
| AIN-BR-14 / Must | Make background job progress and interruption semantics explicit. | Acknowledgment means queued, not complete. Preserve owner-scoped status and documented queue limits; exercise duplicate submission, queued cancellation and cooperative running-stop paths. Restart/restore outcomes match the current job contract without claiming exactly-once failover. | [Jobs](../BACKGROUND_INVESTIGATIONS.md), [stop](../COOPERATIVE_INVESTIGATION_STOP.md), [job tests](../../tests/test_jobs.py). One local worker; running calls are not forcibly interrupted. |
| AIN-BR-15 / Must | Preserve research review and sharing boundaries. | In an isolated account fixture, opted-in second-account sharing follows current role/ownership rules; the author cannot approve their own opted-in peer report. Withdrawal and conflicting review retries preserve the exact recorded outcome. | [Peer review](../SECOND_ACCOUNT_REVIEW.md), [withdrawal](../SHARING_WITHDRAWAL.md), [peer tests](../../tests/test_peer_review.py). Separate accounts are not independently verified people. |
| AIN-BR-16 / Must | Expose instance health and readiness honestly. | Backend outage and stale/invalid monitoring samples cannot appear healthy. Readiness display retains every P01–P24 ID and shows production acceptance false. Report checksums do not mark a gate accepted. | [Monitoring](../MONITORING_INTEGRITY.md), [readiness](../RELEASE_READINESS.md), [readiness tests](../../tests/test_readiness.py). Local observations do not establish a production SLO. |
| AIN-BR-17 / Must | Support a reproducible operator setup and trusted restore. | On a named supported environment, record setup prerequisites and actual startup mode. A fresh clone is not presented as containing data/accounts/models. Restore to a new destination; verify selected state and revoke restored sessions without overwriting the live instance. | [Development](../DEVELOPMENT.md), [recovery](../LOCAL_DEPLOYMENT_RECOVERY.md), [recovery tests](../../tests/test_recovery.py). Full-stack operation on other computers is not assumed. |
| AIN-BR-18 / Should | Preserve bounded encrypted recovery and compatible rollback. | For the chosen supported provider, wrong-key/tampered archive restore fails; existing targets are refused. A rollback drill uses its isolated project/volume and rejects incompatible state contracts or active jobs. Record the exact tested pair. | [Encrypted recovery](../ENCRYPTED_RECOVERY.md), [rollback](../LOCAL_RELEASE_ROLLBACK.md). Off-site/key-loss recovery and database/model/prompt rollback remain outside current qualification. |

## 6. Non-functional requirements

These are proposed acceptance conditions. Numeric service targets below are explicitly **not established** unless already part of a bounded application contract.

| ID / priority | Quality requirement | Acceptance criteria and outstanding decision |
|---|---|---|
| AIN-NFR-01 / Must | Security and privacy | Test role/owner denial, CSRF/origin controls, safe text rendering and secret exclusion with temporary fixtures. Do not put credentials, raw datasets, private artifacts or runtime databases in Git. Independent security/privacy review and deployment threat acceptance remain pending. |
| AIN-NFR-02 / Must | Correctness and integrity | Validate report/contract identities and fail visibly on missing or mismatched evidence. Preserve selected negative research results. Hashes must be described as consistency checks unless an independently verified signing/trust mechanism exists. |
| AIN-NFR-03 / Must | Reproducibility | Record source revision, dependency versions, dataset/protocol identities and exact commands. A fresh CI run must refer to the intended revision; private-data/model-dependent steps are listed separately rather than silently skipped and called passed. |
| AIN-NFR-04 / Must | Performance and capacity | Measure latency/error/resource/queue behavior for a defined workload and environment. Product and engineering owners must agree p95 latency, throughput, concurrency and error budgets before a performance acceptance claim. Existing bounded local measurements are evidence inputs, not universal targets. |
| AIN-NFR-05 / Must | Recovery and reliability | Record restart, interruption, missing-dependency and restore outcomes without corrupting live state. Define acceptable data loss (RPO) and time to restore service (RTO) before production acceptance; local drill timing is not a full-system commitment. |
| AIN-NFR-06 / Must | Usability and accessibility | Verify critical journeys with keyboard navigation, visible focus, readable errors and meaningful labels; document actual browser/viewport and screen-reader scope. Selected 390/433-pixel historic checks do not establish complete accessibility conformance. Formal target and device matrix require owner review. |
| AIN-NFR-07 / Must | Maintainability and change control | Link each material requirement to a module, representative tests, decisions and evidence. Preserve compatible data/migrations and exact-build rollback limits. New features require reviewed changes; document presence is not implementation evidence. |
| AIN-NFR-08 / Must | AI quality and human accountability | Keep development and held-out evaluation separate. Agree representative retrieval/answer relevance, grounding, refusal and analyst-workload criteria before acceptance. A valid quotation, model research-gate pass or positive self-review alone cannot satisfy semantic/operational acceptance. |

No source code or test is altered to make these conditions appear satisfied. In particular, this document does not retune a model, change roles, broaden tool access or amend the readiness catalog.

## 7. Proposed research acceptance journeys

Execute against a disposable local environment and authorised fixtures. These are acceptance scenarios to perform, **not newly recorded passes**.

| Journey | Steps and observable outcome | Requirements |
|---|---|---|
| UAT-01 — Historical evidence | Sign in with the intended read role; inspect source period/counts and recorded audit; compare allowed aggregate export with the pinned report. Verify that missing/tampered evidence is unavailable rather than replaced. | BR-01–04, NFR-01–03 |
| UAT-02 — Model investigation | Inspect train/validation/test periods and baseline comparison; run one supported historical scenario; submit invalid/out-of-scope input and test missing-artifact behavior. Keep the duration model's failed gate visible. | BR-05–07, NFR-02/08 |
| UAT-03 — Synthetic proposal | Compute the declared gate example; verify feasible assignments/baseline; save a research decision; exercise retry, changed-proposal and expiry rejection. No airport action occurs. | BR-08–09, NFR-02 |
| UAT-04 — Bounded AI evidence | Query the approved corpus with an acknowledged scope; inspect citations, refusal and unavailability; run a permitted investigation and a denied-tool case; review the exact retained report. | BR-10–15, NFR-01/08 |
| UAT-05 — Session and display isolation | Change input/account during a pending query or file read; confirm old results do not return. Exercise viewer denial and revoked session behavior. Reopen an unsigned review artifact separately from the live query. | BR-02/11/12/15, NFR-01/06 |
| UAT-06 — Operator recovery | Verify instance identity and health; exercise a temporary dependency outage; restore trusted state into a new instance; check session revocation and selected artifacts. Perform rollback only on its qualified isolated target. | BR-16–18, NFR-03–05/07 |

### Research milestone decision rule

A proposed research milestone may be marked accepted only when:

1. The owner agrees the precise scope and any deferred Should requirements.
2. Every applicable Must criterion has an actual reviewed outcome for the release revision.
3. Failed cases and unresolved defects are listed with their impact and disposition.
4. No unresolved defect defeats identity, owner boundaries, data integrity, scope labeling or the claimed critical journey.
5. AI quality limitations and permitted use are explicitly reviewed, even if mechanical tests pass.
6. A named accountable reviewer records the decision and its limits.

This decision is **research acceptance only**. It cannot close P01–P24 production gates or authorise airline operations.

## 8. Production dependencies and open decisions

| Decision | Proposed accountable role | Required output before broader delivery |
|---|---|---|
| Research vs commercial deployment scope | Product owner and domain reviewer | Approved use cases, exclusions, users and release boundary. |
| Data rights and geography | Data steward and legal/privacy reviewer | Source permissions, lawful purpose, retention/residency and publication policy. No UAE dataset is assumed available. |
| Model and answer quality | Research lead and independent domain reviewer | Frozen evaluation protocol, representative datasets, thresholds, failure costs and review capacity. |
| Identity and tenancy | Security architect and platform owner | IdP/MFA/lifecycle decisions, tenant/site/resource model and denial tests. |
| Cloud and networking | Platform owner | Approved environment, budget, DNS/TLS, secrets, access and deployment boundary. |
| Service and recovery targets | Operations owner | Defined availability/workload/SLO, RPO/RTO, alert routing and operator drill plan. |
| Review authority | Product owner and governance reviewer | Distinct research/self-review/peer-review/operational approval rules and verified authority. |

All roles above remain proposed. Do not invent approvals, data rights, budgets or service-level commitments.

## 9. Traceability and next document

The capability IDs B01–B15 are defined in [AIN-EA-01](01-CURRENT-IMPLEMENTATION-BASELINE.md). BR-01–18 map business needs to representative source/test references; NFR-01–08 define cross-cutting proposed quality conditions. The later traceability matrix will assign exact test functions, evidence versions, owners and acceptance results.

The next document is **AIN-EA-03 — Enterprise Architecture Overview**: current and target business, application, data, AI, security and infrastructure views, preserving the scope and decisions above. No new architecture file is implied to exist until it is committed.

## 10. Change control and sign-off record

| Field | Current state |
|---|---|
| Scope proposer | Prepared for repository-owner review; no named approval asserted |
| Business/domain approval | Pending |
| Requirement acceptance executions in this change | None |
| New software/model/deployment changes | None |
| Production gate acceptance | 0 of 24; unchanged |
| Open defects and evidence | Existing milestone limitations and readiness catalog remain authoritative within their stated scope |
| Refresh trigger | Material change to business scope, data, runtime, model, identity, tools, review authority or release boundary |

Review changes to these requirements through a versioned commit. Preserve original experimental protocols and historical results; document a new experiment rather than rewriting old evidence.
