# AIN-EA-05 — Architecture Decision Records

**Project:** Aviation Intelligence Nexus (AIN)  
**Recorded:** 26 November 2026, Dubai  
**Reviewed revision:** [`816bfb5`](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/tree/816bfb5045c35728a9e1899afbfe35acca45fd3d)  
**Document status:** Retrospective records of observed choices plus an open decision queue; no historical stakeholder approval invented  
**Change scope:** Documentation only; no application behavior, protocols, credentials, state, deployment or production gates changed.

[Baseline](01-CURRENT-IMPLEMENTATION-BASELINE.md) · [Business requirements](02-BUSINESS-REQUIREMENTS-AND-ACCEPTANCE.md) · [Enterprise overview](03-ENTERPRISE-ARCHITECTURE-OVERVIEW.md) · [System diagrams](04-SYSTEM-ARCHITECTURE-DIAGRAMS.md) · [Project README](../../README.md)

## How these records should be used

An architecture decision record explains a consequential choice, its context, alternatives, consequences and review trigger. These records capture what the repository implements now. They are **not** contemporaneous minutes of the original implementation decision, named stakeholder approvals, production acceptance or a promise that every alternative was previously evaluated.

Benefits and alternative comparisons below are current architectural analysis inferred from the observed structure. Existing protocols and explicit runtime restrictions are grounded in the linked source. All source evidence links are pinned to the reviewed revision so later code changes do not silently alter this record.

Each record has the same status: **observed implementation / retrospective / owner review pending**. Future decisions use **proposed** until actual evidence and accountable review justify a change. Implementation existence, a green test and an accepted business decision are separate states.

### Decision register

| ID | Topic | Status |
|---|---|---|
| AIN-ADR-001 | Keep a modular local research application | Observed; retrospective; review pending |
| AIN-ADR-002 | Use private SQLite state and separate trusted artifacts | Observed; retrospective; review pending |
| AIN-ADR-003 | Route browser research calls through a fixed local proxy | Observed; retrospective; review pending |
| AIN-ADR-004 | Use explicit local accounts, sessions and scoped roles | Observed; retrospective; review pending |
| AIN-ADR-005 | Freeze temporal experiment selection before held-out evaluation | Observed; retrospective; review pending |
| AIN-ADR-006 | Fail closed on unsupported historical inference and artifact mismatch | Observed; retrospective; review pending |
| AIN-ADR-007 | Keep local RAG evidence constrained and semantic acceptance separate | Observed; retrospective; review pending |
| AIN-ADR-008 | Execute a bounded custom single agent with validated tools | Observed; retrospective; review pending |
| AIN-ADR-009 | Keep synthetic gate optimization separate from real operational action | Observed; retrospective; review pending |
| AIN-ADR-010 | Use loopback local deployment and exact-build bounded CI evidence | Observed; retrospective; review pending |
| AIN-ADR-011 | Restore to new destinations and isolate compatible application rollback | Observed; retrospective; review pending |
| AIN-ADR-012 | Separate evidence integrity, research acceptance and production approval | Observed; retrospective; review pending |

## AIN-ADR-001 — Keep a modular local research application

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-01/13/14/17; NFR-03/07

**Context.** The source combines a Node web/proxy process and Python FastAPI research application. ML, retrieval, optimization and agent packages remain explicit modules; the bounded background worker is attached to the API.

**Current decision boundary.** Record the observed modular process structure as the current research architecture. Preserve all 64 demonstration workspaces while identifying connected services separately.

**Alternatives for review.** Separate microservices with a broker; a frontend-only demonstration; a single process serving every layer. These are retrospective comparison options, not evidence of a historical selection meeting.

**Benefit.** Module boundaries permit targeted tests and local setup without a multi-service orchestration platform.

**Cost and limitations.** Attached workers share API lifetime/resources. Local process and storage limits constrain isolation, concurrency and availability.

**Evidence:** [API](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/services/api/main.py) · [Local launcher](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/scripts/start-local.mjs) · [Jobs](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/agents/jobs.py) · [Application diagrams](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/enterprise-architecture/04-SYSTEM-ARCHITECTURE-DIAGRAMS.md).

**Revisit trigger.** Reconsider decomposition when a measured workload, trust boundary, independent release cadence or availability target requires it; obtain failure/load evidence before claiming the replacement is better.

## AIN-ADR-002 — Use private SQLite state and separate trusted artifacts

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-03/14/17/18; NFR-01–03/05

**Context.** The local implementation persists accounts, historical flight rows, research histories, proposals and job records in private SQLite state, with model/index files and selected reports outside the database.

**Current decision boundary.** Document SQLite and separate artifact files as the implemented local persistence arrangement. Keep raw data, fitted artifacts, accounts, runtime state and keys outside Git; publish only appropriate sanitized aggregate evidence.

**Alternatives for review.** Managed relational database plus object storage; embedded analytical storage; an external lakehouse. None is selected for deployment by this record.

**Benefit.** Local transactions, inspectable migrations and a reproducible small-system boundary support research development.

**Cost and limitations.** Local storage and attached jobs do not provide managed HA, independent disaster recovery or automatically atomic database/model/index snapshots. File identities and consistency must be verified across a restore.

**Evidence:** [State paths](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/services/api/paths.py) · [Agent state](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/agents/store.py) · [Recovery](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/infra/recovery.py) · [Recovery runbook](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/LOCAL_DEPLOYMENT_RECOVERY.md).

**Revisit trigger.** Choose managed persistence only after defining tenancy, concurrency, retention, recovery and availability needs; require migration and restore evidence.

## AIN-ADR-003 — Route browser research calls through a fixed local proxy

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-02/06/10–16; NFR-01/07

**Context.** The web layer recognizes specific research endpoints, method/body constraints and permitted session/CSRF metadata. The browser does not choose an arbitrary proxy destination.

**Current decision boundary.** Retain the explicit Node proxy boundary and independent API validation for the local application. Treat UI visibility and proxy filtering as supplementary to server-side authority.

**Alternatives for review.** Browser-to-API calls with a cross-origin contract; a general gateway; an unrestricted forwarding proxy. The unrestricted option would expand authority beyond the present design.

**Benefit.** A predictable browser origin and a small forwarding surface make the local request contract easier to inspect and test.

**Cost and limitations.** Route additions need coordinated proxy and API changes. Same-origin transport does not eliminate CSRF, permission, session or deployment concerns.

**Evidence:** [Fixed proxy](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/scripts/api-proxy.mjs) · [API handlers](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/services/api/main.py) · [Dashboard/proxy tests](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/tests/test_dashboard.mjs) · [Browser policies](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/LOCAL_BROWSER_SECURITY.md).

**Revisit trigger.** Review gateway/proxy topology when introducing an approved external domain, API consumers or managed identity. Do not silently broaden the local forwarding contract.

## AIN-ADR-004 — Use explicit local accounts, sessions and scoped roles

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-02/11–15; NFR-01

**Context.** The research application uses locally provisioned admin/researcher/viewer accounts and server-side session/role/owner checks, with account/session revocation behavior.

**Current decision boundary.** Document local authentication as an implemented research control, not enterprise identity acceptance. No default password, browser-only role selector or separate login is evidence of airline authority.

**Alternatives for review.** Managed OIDC/SSO/MFA with a governed lifecycle; anonymous demonstration mode; client-side-only access control. Managed identity remains a target decision.

**Benefit.** Local provisioning and negative permission tests enable bounded research workflows without a production identity platform.

**Cost and limitations.** Local administration does not establish verified independent humans, enterprise joiner/mover/leaver processes, service identity or complete tenant isolation.

**Evidence:** [Identity runbook](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/LOCAL_IDENTITY.md) · [Auth](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/services/api/auth.py) · [User administration](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/services/api/manage_users.py) · [Auth tests](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/tests/test_auth.py) · [Account security tests](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/tests/test_account_security.py).

**Revisit trigger.** Agree a pilot's identity provider, MFA/lifecycle, resource scope and reviewer authority before enterprise deployment.

## AIN-ADR-005 — Freeze temporal experiment selection before held-out evaluation

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-05–07; NFR-02/03/08

**Context.** The v2 delay experiment declares January–March 2025 training, April validation and May test, with explicit features, candidates, comparator and a research gate.

**Current decision boundary.** Preserve the existing frozen protocol and report identities. Select using April and evaluate the frozen choice on May. Keep v1 and the failed duration experiment as historical evidence; later changes require a new experiment and appropriate future evaluation.

**Alternatives for review.** Random splits across periods; selection against the already evaluated test period; online retraining without a governed protocol. Those alternatives do not preserve the present temporal evidence boundary.

**Benefit.** Temporal separation and retained negative results make research comparisons interpretable and reduce avoidable evaluation leakage.

**Cost and limitations.** Five historical US months do not establish seasonal or UAE airline generalisation. A passed research gate does not resolve calibration, false-alert burden or operational decision cost.

**Evidence:** [v2 protocol](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/ml/experiment_v2.json) · [v2 training](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/ml/train_v2.py) · [v2 results](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/DELAY_V2.md) · [Duration negative result](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/DELAY_DURATION_REGRESSION.md) · [v2 tests](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/tests/test_v2.py).

**Revisit trigger.** A new period/population, target, feature set, calibration or threshold study needs its own frozen evaluation design; do not recycle May as an untouched holdout.

## AIN-ADR-006 — Fail closed on unsupported historical inference and artifact mismatch

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-05/06; NFR-01–03/08

**Context.** The predictor restricts scenario dates, input fields and vocabulary, and uses a fixed trusted local model/report identity rather than a request-selected artifact.

**Current decision boundary.** Keep historical scenario validation and artifact/report verification ahead of inference. Return rejection/unavailability rather than inventing a fallback probability or accepting an arbitrary model upload.

**Alternatives for review.** Unbounded future/airport predictions; user-selected serialized model files; silent synthetic scores. These would require different scope, validation and trust decisions.

**Benefit.** Response scope and model identity remain traceable to the documented research artifact.

**Cost and limitations.** Missing private artifacts make a fresh clone's predictor unavailable. Hash agreement does not protect against an administrator replacing both artifact and report, and trusted serialization still requires a safe source.

**Evidence:** [Predictor](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/services/api/prediction.py) · [Prediction contract](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/RESEARCH_PREDICTION.md) · [Prediction tests](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/tests/test_prediction.py).

**Revisit trigger.** Extend serving only after representative evaluation, a reviewed artifact trust/promotion policy, operational scope and qualified model rollback.

## AIN-ADR-007 — Keep local RAG evidence constrained and semantic acceptance separate

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-10–12; NFR-01/02/08

**Context.** The research index covers approved public project documents. Optional local generation, scoped excerpt selection, scope/coverage checks and browser review have explicit known limitations.

**Current decision boundary.** Preserve allowlisted source/index boundaries and cite the exact recorded evidence. Keep original Q&A, scoped candidates and self-review/inspection distinct. Exact quotation or checksum consistency must not be represented as semantic correctness.

**Alternatives for review.** Arbitrary upload/web retrieval; unchecked free-form answers; treating a self-review label as independent acceptance. Each would expand the current evidence/authority boundary.

**Benefit.** A bounded corpus and exact evidence make failure analysis and evaluation more reproducible.

**Cost and limitations.** Coverage gates can reject valid paraphrases or miss unsupported short topics. An exact quote can be irrelevant or incomplete. Unsigned exported judgments do not verify identity.

**Evidence:** [Knowledge studio](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/KNOWLEDGE_STUDIO.md) · [Scoped lab](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/SCOPED_ANSWER_LAB.md) · [Source coverage](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/SOURCE_COVERAGE_GATE.md) · [Self-review](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/SCOPED_SELF_REVIEW.md) · [Inspector tests](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/tests/test_scoped_review.mjs).

**Revisit trigger.** Approve corpus rights/ACL lifecycle, relevance/refusal/grounding criteria and independent semantic evaluation before expanding sources or claiming business suitability.

## AIN-ADR-008 — Execute a bounded custom single agent with validated tools

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-10/13/14; NFR-01/04/08

**Context.** A local Ollama-assisted runtime proposes typed tools. Server code checks allowlists, canonical arguments, explicit user scope and conditional opt-ins before executing bounded research tools.

**Current decision boundary.** Document the custom single-agent runtime as implemented. Do not claim LangGraph, a multi-agent platform, arbitrary executable SQL/shell access or autonomous airline control. Keep queue, timeout, permission and cooperative-stop limits explicit.

**Alternatives for review.** A graph framework or distributed worker system; a deterministic non-model workflow; unrestricted model-directed execution. No framework migration is approved here.

**Benefit.** Tool authority is small and inspectable; evidence, checkpoints and retained failures can be reviewed.

**Cost and limitations.** One local API worker and bounded waiting limits are not distributed leases/failover. A running model/tool call is not forcibly interrupted by a cooperative stop. Tool completion does not prove objective completeness.

**Evidence:** [Runtime](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/agents/runtime.py) · [Tools](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/agents/tools.py) · [Jobs](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/agents/jobs.py) · [Job contract](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/BACKGROUND_INVESTIGATIONS.md) · [Quality limits](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/AGENT_REPORT_QUALITY.md) · [Agent tests](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/tests/test_agent.py).

**Revisit trigger.** Use measured quality/resource/failure needs to justify framework or worker changes; maintain argument/scope tests and authority limits through any migration.

## AIN-ADR-009 — Keep synthetic gate optimization separate from real operational action

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-08/09/15; NFR-02/08

**Context.** The solver handles bounded synthetic flights/gates and independent feasibility/accounting checks. Research review binds to the exact saved proposal and its original expiry.

**Current decision boundary.** Preserve synthetic labels, independent plan checks and the research-only decision vocabulary. A solver result, a review receipt or a second account must not dispatch a real airport allocation.

**Alternatives for review.** Actual airport integration; unvalidated heuristic-only results; automatic effect after generation. Real constraints and action authority need separate approval and evidence.

**Benefit.** A small research case can compare an optimizer and baseline without misrepresenting operational constraints or benefits.

**Cost and limitations.** Toy scenario coverage is limited. Self-review is permitted in the synthetic gate workflow; opted-in peer investigation review has different rules. These controls must not be conflated.

**Evidence:** [Solver](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/optimization/gates.py) · [Gate reviews](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/optimization/reviews.py) · [Gate lab](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/GATE_OPTIMIZATION.md) · [Review contract](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/GATE_PROPOSAL_REVIEW.md) · [Peer-review boundary](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/SECOND_ACCOUNT_REVIEW.md) · [Solver tests](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/tests/test_gates.py).

**Revisit trigger.** Require authorised airport data/constraints, independently reviewed feasibility, workload results and explicit human/business authority before proposing any live effect.

## AIN-ADR-010 — Use loopback local deployment and exact-build bounded CI evidence

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-16/17; NFR-01/03–05/07

**Context.** Native development and the Docker release have distinct launchers and ports. Compose exposes the web service on loopback and keeps the API unpublished. CI runs source/Node, Python and container checks using temporary/synthetic state.

**Current decision boundary.** Retain those local deployment boundaries and record evidence against the exact revision/environment. Keep host Ollama and private artifacts as separate prerequisites. Do not equate container hardening or green CI with production qualification.

**Alternatives for review.** An internet-facing unmanaged development server; approved cloud staging with managed services; a full Kubernetes platform. Cloud/Kubernetes are unselected target options.

**Benefit.** Local isolation and reproducible checks establish a bounded engineering foundation without assuming cloud authority or costs.

**Cost and limitations.** Local availability and host-runtime compatibility do not meet enterprise SLOs by default. CI does not retrain million-row models, verify host AI semantic quality or accept live airline integration.

**Evidence:** [Compose](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/compose.yaml) · [CI](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/.github/workflows/checks.yml) · [Development](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/DEVELOPMENT.md) · [Local deployment](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/LOCAL_DEPLOYMENT_RECOVERY.md) · [Deployment verifier](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/infra/verify_deployment.py).

**Revisit trigger.** Select cloud/network/identity/storage only after environment authority, budgets, data rights and workload/recovery objectives are defined.

## AIN-ADR-011 — Restore to new destinations and isolate compatible application rollback

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** BR-17/18; NFR-01–03/05/07

**Context.** Recovery uses trusted snapshots and no-overwrite destinations; encrypted recovery uses a supported local key provider. Rollback targets a dedicated project/volume and compatible retained image identities.

**Current decision boundary.** Preserve live-state separation and exact-pair compatibility checks. Treat encrypted restore, plaintext snapshots, isolated application rollback and runtime drill receipts as distinct mechanisms with separate coverage.

**Alternatives for review.** In-place overwriting of live state; automatic arbitrary database/model downgrade; a future managed off-site backup/escrow system. No expanded recovery authority is granted.

**Benefit.** Drills can inspect selected recovered state and behavior without silently replacing primary user data.

**Cost and limitations.** Windows DPAPI dependence does not establish independent key recovery. Plaintext originals remain. Selected image/state-contract compatibility does not qualify universal rollback, full-system RTO or computer-loss recovery.

**Evidence:** [Recovery](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/infra/recovery.py) · [Encrypted recovery](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/infra/sealed_recovery.py) · [Release controller](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/infra/releases.py) · [Encrypted runbook](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/ENCRYPTED_RECOVERY.md) · [Rollback runbook](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/LOCAL_RELEASE_ROLLBACK.md) · [Recovery tests](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/tests/test_recovery.py).

**Revisit trigger.** Define RPO/RTO, off-site retention, independent key escrow and target-environment restore evidence before a disaster-recovery commitment.

## AIN-ADR-012 — Separate evidence integrity, research acceptance and production approval

**Status:** Observed in current implementation; retrospective record; owner review pending  
**Recorded:** 26 November 2026, Dubai  
**Requirement linkage:** All BRs; NFR-02/03/07/08

**Context.** The readiness implementation retains 24 fixed production requirements with acceptance false. Public reports, selected hashes, exact-build receipts and local research reviews have different proof limits.

**Current decision boundary.** Use baseline/requirements/architecture/source/test/evidence links to explain scope, not to manufacture acceptance. Preserve all P01–P24 states until a real accountable acceptance process exists. Keep candidate, negative and unavailable results visible.

**Alternatives for review.** Completion percentages inferred from file counts; auto-acceptance after hash checks; marking every roadmap preview implemented. Those approaches overstate available evidence.

**Benefit.** Reviewers can see both engineering progress and what remains unqualified.

**Cost and limitations.** Maintaining current-vs-historical evidence is ongoing work. A signed-off enterprise release requires external decisions and measurements beyond repository documentation.

**Evidence:** [Readiness code](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/infra/readiness.py) · [Gate catalog](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/infra/readiness.json) · [Readiness meaning](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/RELEASE_READINESS.md) · [Baseline](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/enterprise-architecture/01-CURRENT-IMPLEMENTATION-BASELINE.md) · [Requirements](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/816bfb5045c35728a9e1899afbfe35acca45fd3d/docs/enterprise-architecture/02-BUSINESS-REQUIREMENTS-AND-ACCEPTANCE.md).

**Revisit trigger.** Update when a reviewed scope/environment or acceptance authority changes; retain old evidence rather than rewriting historical results.

## Future decision queue — proposed, not selected

| ID | Decision needed | Alternatives to evaluate | Required input and exit evidence |
|---|---|---|---|
| AIN-ADR-P01 | Enterprise identity and resource isolation | Approved managed IdP, lifecycle, tenancy/site model and policy options | Product/security owners, pilot user roles, data boundaries; deployed sign-in/revocation/denial tests and independently reviewed authority model |
| AIN-ADR-P02 | Managed persistence and artifact storage | Retain local SQLite for research or migrate the approved pilot to managed relational/object storage | Measured workload, concurrency, retention and RPO/RTO; migration, access isolation and restore evidence |
| AIN-ADR-P03 | Worker isolation and durable execution | Keep attached bounded worker, separate worker process or adopt a governed queue/orchestrator | Capacity/failure data, allowed effects, leases/retry/compensation requirements; crash/duplicate/recovery tests |
| AIN-ADR-P04 | AI runtime, corpus and semantic acceptance | Approved local or hosted runtime; evaluated embedding/retrieval/generation paths | Rights, resource/cost/privacy constraints, frozen representative datasets, relevance/grounding/refusal metrics and independent review |
| AIN-ADR-P05 | Cloud staging, monitoring and release controls | Approved environment/network/secret/observability choices; avoid premature service decomposition | Account authority, budget, workload/SLOs, operators; exact-build deployment, alert, load, rollback and incident drills |
| AIN-ADR-P06 | Independent recovery and key lifecycle | Governed off-site backup, portable escrow or approved managed key design | Threat model, retention, RPO/RTO, accountable key custodians; wrong-key/tamper tests and independent computer/environment recovery |

No cloud vendor, managed database, queue, identity provider, model provider or additional agent framework is selected by this queue.

## Change and supersession procedure

1. Identify the affected ADR and business requirement before changing its source boundary.
2. State the new context and measurable reason; distinguish an implementation fix from an architectural replacement.
3. Document actual evaluated alternatives and evidence, including failed results, cost and migration implications.
4. Identify the accountable reviewer and record the decision/date only when real review occurs.
5. Add a new ADR or explicitly supersede the old record; preserve its original revision and rationale.
6. Update architecture diagrams and requirement-to-code/test references.
7. Run relevant checks for the actual source change; documentation-only edits must not imply a new runtime verification.
8. Reassess applicable production obligations without auto-closing a gate.

## Verification of this documentation change

- Existing repository instructions and source-tree references were checked at the reviewed revision.
- Source/configuration/test links are pinned to that revision and checked for existence.
- Record IDs AIN-ADR-001 through AIN-ADR-012 are unique; six proposed future decisions use distinct P-prefixed IDs.
- No test suite, model training, browser review, restore or deployment was executed for these retrospective records.
- No underlying implementation approval or production acceptance is asserted.

**Next planned document:** AIN-EA-06 — Data Architecture and Governance, covering current data classes, source rights/provenance, storage, schemas, lifecycle, access and retention decisions.
