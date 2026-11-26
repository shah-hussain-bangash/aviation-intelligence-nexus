# AIN-EA-10 — Requirements Traceability Matrix

**Project:** Aviation Intelligence Nexus (AIN)  
**Date:** 26 November 2026, Dubai  
**Reviewed source revision:** [`37e983e`](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/tree/37e983ee02967132adb1dc9c3d118ea8b2a27368)  
**Status:** Source/test/evidence linkage review; owner-reviewed research and production acceptance remain pending  
**Change scope:** Documentation only. No application behavior, tests, experiments, private state, deployment or gate values changed.

[Requirements](02-BUSINESS-REQUIREMENTS-AND-ACCEPTANCE.md) · [Baseline](01-CURRENT-IMPLEMENTATION-BASELINE.md) · [Architecture](03-ENTERPRISE-ARCHITECTURE-OVERVIEW.md) · [Decisions](05-ARCHITECTURE-DECISION-RECORDS.md) · [Engineering handbook](09-SOFTWARE-ENGINEERING-HANDBOOK.md)

## 1. Purpose and evidence meaning

This matrix links the **18 business requirements** and **8 non-functional requirements** in AIN-EA-02 to current source, a representative test, evidence/runbooks, architecture decisions and acceptance gaps.

A link is not a proof of complete requirement coverage. Each row identifies an entry point for review, not every relevant source line, test function or failure mode. Broad requirements need multiple tests, deployment exercises and independent review.

Source/test/evidence links are pinned to the reviewed revision. Representative test names were checked against file contents; they were **not executed** for this documentation change. A test file or historical report does not establish current runtime behavior, semantic correctness, independent approval or production suitability.

All 26 requirement rows have **acceptance pending**. That does not erase existing local implementations or earlier scoped test passes; it means this newly proposed owner-reviewed requirement acceptance has not been performed and recorded.

### Reference conventions

- **B01–B15:** capability entries in [AIN-EA-01](01-CURRENT-IMPLEMENTATION-BASELINE.md).
- **ADR-001–012:** shorthand for AIN-ADR-001 through AIN-ADR-012 in [AIN-EA-05](05-ARCHITECTURE-DECISION-RECORDS.md).
- **P01–P24:** existing production readiness requirements, separate from BR/NFR acceptance.
- **Evidence / scope:** an implementation/experiment/runbook record with its own limitations; not a new signed acceptance artifact.
- No completion or test-coverage percentage is calculated from row counts.

## 2. Business requirement matrix

| Requirement | Business need | Implementation entry | Representative test (not newly run) | Evidence / boundary | Capability / decision / gate | Remaining acceptance work |
|---|---|---|---|---|---|---|
| AIN-BR-01 | Demo versus connected-service scope | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/apps/web/app.js) | [File-level representative coverage](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_dashboard.mjs) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/CONNECTED_DASHBOARD.md) | B01; ADR-001/012; P11/P24 | UI preservation and origin labels exist; owner walkthrough of each selected critical panel is pending. **Acceptance pending.** |
| AIN-BR-02 | Authenticated role and owner access | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/services/api/auth.py) | [test_owner_scoping_and_legacy_admin_visibility](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_auth.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/LOCAL_IDENTITY.md) | B02; ADR-004; P12/P13 | Local controls exist; full route/resource denial matrix, managed identity and applicable tenant qualification remain. **Acceptance pending.** |
| AIN-BR-03 | Validated, repeatable historical ingestion | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/pipelines/import_bts.py) | [test_repeat_import_does_not_duplicate_and_missing_delays_stay_null](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_ingestion.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/LOCAL_DATA_INTAKE.md) | B03; ADR-002; P03/P04 | Local importer/intake exist; source-rights review and operator-owned acceptance remain. **Acceptance pending.** |
| AIN-BR-04 | Understandable data quality and lineage | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/pipelines/audit_quality.py) | [test_recorded_actual_report_pinned_with_frozen_population_counts](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_data_quality.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/DATA_QUALITY_LINEAGE.md) | B03; ADR-012; P03/P04 | Pinned structural evidence exists; source truth, complete row identity and independent stewardship remain unestablished. **Acceptance pending.** |
| AIN-BR-05 | Temporal model protocol and baseline integrity | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/ml/train_v2.py) | [test_protocol_hash_and_temporal_boundaries](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_v2.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/DELAY_V2.md) | B04/B05; ADR-005; P06 | Frozen historical experiment exists; future-population/domain acceptance and newly agreed quality criteria remain. **Acceptance pending.** |
| AIN-BR-06 | Bounded historical inference and provenance | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/services/api/prediction.py) | [test_real_inference_has_bounds_provenance_and_research_warning](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_prediction.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/RESEARCH_PREDICTION.md) | B04; ADR-006; P07 | Local inference and rejection paths exist; operational population, calibration and exact deployed journey acceptance remain. **Acceptance pending.** |
| AIN-BR-07 | Retrospective diagnostics and route lookup | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/services/api/route_history.py) | [test_readonly_counts_denominators_clipping_and_fixed_periods](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_route_history.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/HISTORICAL_ROUTE_LOOKUP.md) | B06; ADR-005/006; P05/P06 | Bounded lookup/report analysis exists; independent interpretation and complete selected diagnostic walkthrough remain. **Acceptance pending.** |
| AIN-BR-08 | Feasible synthetic gate proposal | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/optimization/gates.py) | [test_solution_matches_exhaustive_small_problem_oracle](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_gates.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/GATE_OPTIMIZATION.md) | B07; ADR-009; P10 | Small synthetic scenarios and checker exist; real constraints, scale and airport domain acceptance are outside current qualification. **Acceptance pending.** |
| AIN-BR-09 | Exact, expiring synthetic research decision | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/optimization/reviews.py) | [test_changed_content_recomputed_invalid_plan_and_extended_expiry_are_blocked](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_gate_review.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/GATE_PROPOSAL_REVIEW.md) | B07; ADR-009; P14 | Bound research decision exists; independent operational authority is neither provided nor accepted. **Acceptance pending.** |
| AIN-BR-10 | Allowlisted retrieval with traceable citations | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/rag/service.py) | [test_explicit_document_scope_keeps_context_inside_the_allowlist](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_knowledge.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/KNOWLEDGE_STUDIO.md) | B08; ADR-007; P08 | Local retrieval/quote checks exist; independent relevance, source applicability and corpus lifecycle acceptance remain. **Acceptance pending.** |
| AIN-BR-11 | Scoped answer uncertainty and stale-result handling | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/services/api/scoped_lab.py) | [test_revoked_session_during_execution_withholds_answer](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_scoped_lab.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/SCOPED_ANSWER_LAB.md) | B09; ADR-007; P08/P13 | Opt-in scoped route exists; false refusals/blind spots and complete target-device/semantic review remain. **Acceptance pending.** |
| AIN-BR-12 | Transparent local self-review and inspection | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/apps/web/scoped-review-import.mjs) | [local file inspector bounds reads and rejects malformed, changed and oversized content](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_scoped_review.mjs) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/REVIEW_FILE_INSPECTOR.md) | B10; ADR-007/012; P14/P16 | Unsigned browser-local artifact checks exist; verified author identity and independent semantic acceptance are not claimed. **Acceptance pending.** |
| AIN-BR-13 | Bounded, permitted research tools | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/agents/runtime.py) | [test_shell_unknown_sql_and_month_scope_are_rejected_before_execution](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_agent.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/INVESTIGATION_AGENT.md) | B11; ADR-008; P09 | Custom single-agent boundary exists; adversarial completeness and independent domain/task acceptance remain. **Acceptance pending.** |
| AIN-BR-14 | Job progress, deduplication and interruption semantics | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/agents/jobs.py) | [test_cancellation_is_owner_checked_and_running_stop_is_requested_cooperatively](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_jobs.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/BACKGROUND_INVESTIGATIONS.md) | B12; ADR-008; P09 | Bounded local jobs exist; distributed leases/failover and representative crash/load acceptance remain. **Acceptance pending.** |
| AIN-BR-15 | Research sharing and exact-report review | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/agents/review_access.py) | [test_current_role_and_session_are_rechecked_inside_review_transaction](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_peer_review.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/SECOND_ACCOUNT_REVIEW.md) | B12; ADR-009; P13/P14 | Scoped review/withdrawal behavior exists; different accounts do not verify independent people or business authority. **Acceptance pending.** |
| AIN-BR-16 | Honest runtime/readiness state | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/infra/readiness.py) | [test_complete_scope_is_not_a_production_acceptance_and_handles_windows_line_endings](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_readiness.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/RELEASE_READINESS.md) | B14/B15; ADR-012; P18/P24 | Read-only gates and local monitor exist; independent uptime, external alerts and all production approvals remain open. **Acceptance pending.** |
| AIN-BR-17 | Reproducible setup and trusted isolated restore | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/infra/recovery.py) | [test_restore_verifies_artifacts_accounts_and_revokes_only_restored_sessions](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_recovery.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/LOCAL_DEPLOYMENT_RECOVERY.md) | B13; ADR-010/011; P17/P19/P23 | Supported local tools/drills exist; independent operator setup and target-environment acceptance remain. **Acceptance pending.** |
| AIN-BR-18 | Bounded encryption and compatible application rollback | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/infra/releases.py) | [test_schema_contract_changes_or_active_jobs_block_rollback](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_releases.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/LOCAL_RELEASE_ROLLBACK.md) | B13/B14; ADR-011; P19/P20 | Selected local pairs and encryption are documented; independent key recovery, off-site and model/prompt rollback remain unqualified. **Acceptance pending.** |

## 3. Non-functional requirement matrix

| Requirement | Quality need | Implementation entry | Representative test (not newly run) | Evidence / boundary | Capability / decision / gate | Remaining acceptance work |
|---|---|---|---|---|---|---|
| AIN-NFR-01 | Security and privacy | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/services/api/main.py) | [test_origin_and_csrf_are_required_for_mutations](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_auth.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/enterprise-architecture/08-SECURITY-AND-THREAT-MODEL.md) | ADR-003/004; P12/P13/P16 | Representative local checks exist; no complete security/privacy/legal or penetration-test acceptance. **Acceptance pending.** |
| AIN-NFR-02 | Correctness and integrity | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/infra/readiness.py) | [test_unsafe_paths_missing_requirements_and_fabricated_acceptance_are_rejected](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_readiness.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/RELEASE_READINESS.md) | ADR-005/006/012; P06/P15/P22 | Integrity/negative cases exist; hashes are not signatures or semantic truth. **Acceptance pending.** |
| AIN-NFR-03 | Reproducibility | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/scripts/python-checks.mjs) | [test_protocol_hash_and_temporal_boundaries](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_v2.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/DEVELOPMENT.md) | ADR-005/010; P22/P23 | Commands, protocols and CI exist; fresh supported-host/private-state reproduction must be evidenced separately. **Acceptance pending.** |
| AIN-NFR-04 | Performance and capacity | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/agents/jobs.py) | [test_waiting_limits_apply_per_owner_and_globally](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_jobs.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/LOCAL_HTTP_PERFORMANCE.md) | ADR-008/010; P21 | Bounds/local measurements exist; p95, throughput, concurrency and error budgets need owner agreement and representative evaluation. **Acceptance pending.** |
| AIN-NFR-05 | Recovery and reliability | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/infra/sealed_recovery.py) | [test_wrong_key_and_modified_truncated_or_appended_ciphertext_leave_no_target](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_sealed_recovery.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/ENCRYPTED_RECOVERY.md) | ADR-011; P18/P19/P20 | Local integrity/drills exist; agreed RPO/RTO, independent computer/key recovery and target failure drills remain. **Acceptance pending.** |
| AIN-NFR-06 | Usability and accessibility | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/apps/web/index.html) | [real frontend headers cover HTML, HEAD, module, CSS, image and health responses](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_security_headers.mjs) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/REVIEW_FILE_INSPECTOR.md) | B01/B10; P21 | Selected browser receipts and transport tests exist. The cited header test is only supporting transport evidence, not accessibility coverage; keyboard/screen-reader/device acceptance remains. **Acceptance pending.** |
| AIN-NFR-07 | Maintainability and change control | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/scripts/sync-plan.mjs) | [test_schema_contract_changes_or_active_jobs_block_rollback](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_releases.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/GITHUB_SYNC.md) | ADR-001/010/011; P20/P23 | Source/sync/release conventions exist; full maintained requirement/test mapping, owner review and current-build qualification remain ongoing. **Acceptance pending.** |
| AIN-NFR-08 | AI quality and human accountability | [Source](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/agents/quality.py) | [test_failed_repair_cannot_be_accepted_even_with_forged_cached_quality](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/tests/test_agent.py) | [Evidence / scope](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/37e983ee02967132adb1dc9c3d118ea8b2a27368/docs/AGENT_REPORT_QUALITY.md) | ADR-005/007/008/012; P06/P08/P09/P14 | Mechanical quality gates exist; representative independent semantic/domain evaluation and verified review authority remain pending. **Acceptance pending.** |

For NFR-06, HTTP/header checks are explicitly **not** keyboard, screen-reader or usability tests. Existing selected browser receipts can inform a later device/accessibility matrix but cannot substitute for that acceptance exercise.

For NFR-07, a release compatibility test covers only part of maintainability/change control. The reviewed handbook, ADRs, Git practices and maintained traceability are additional evidence, with accountable review still needed.

## 4. Research acceptance journeys and cross-cutting checks

These journeys originate in AIN-EA-02. None was executed or marked passed by this document.

| Journey | Requirement linkage | Evidence to collect for actual acceptance |
|---|---|---|
| UAT-01 — Historical evidence | BR-01–04; NFR-01–03 | Supported-user walkthrough; source/count/provenance reconciliation; missing/tampered evidence outcomes and allowed aggregate export |
| UAT-02 — Model investigation | BR-05–07; NFR-02/08 | Frozen split/protocol/report identities; supported/invalid/unavailable scenario behavior; preserved failed duration gate; independent interpretation |
| UAT-03 — Synthetic proposal | BR-08–09; NFR-02 | Declared synthetic cases; independent feasibility/accounting; retry, altered proposal and original expiry behavior |
| UAT-04 — Bounded AI evidence | BR-10–15; NFR-01/08 | Approved corpus/scope; refusal/unavailability; denied tool; retained evidence and exact-report review with semantic limitations |
| UAT-05 — Session/display isolation | BR-02/11/12/15; NFR-01/06 | Input/account/role changes during pending work; stale display/export suppression; local imported artifact separation; accessibility/device results |
| UAT-06 — Operator recovery | BR-16–18; NFR-03–05/07 | Exact instance/build; controlled temporary outage; isolated trusted restore, session/artifact checks and qualified rollback target |

A UAT receipt must identify whether a model call, real local inference, fixture response or recorded report was used. A mocked success must not be described as a successful live local model invocation.

## 5. Production gate crosswalk

This is a **partial relationship map**, not proof that research requirements fully decompose enterprise production scope. Gates without a direct mapping require their own scope/requirements elaboration.

| Gate | Production area | Related research requirement rows | Current acceptance |
|---|---|---|---|
| P01 | Backend services | Not fully decomposed into the current research requirements; separate production scope review needed. | Open; no acceptance asserted |
| P02 | Persistent database | Not fully decomposed into the current research requirements; separate production scope review needed. | Open; no acceptance asserted |
| P03 | Authorized datasets | AIN-BR-03, AIN-BR-04 | Open; no acceptance asserted |
| P04 | Data ingestion | AIN-BR-03, AIN-BR-04 | Open; no acceptance asserted |
| P05 | Big-data processing | AIN-BR-07 | Open; no acceptance asserted |
| P06 | Data science models | AIN-BR-05, AIN-BR-07, AIN-NFR-02, AIN-NFR-08 | Open; no acceptance asserted |
| P07 | Prediction deployment | AIN-BR-06 | Open; no acceptance asserted |
| P08 | Generative AI | AIN-BR-10, AIN-BR-11, AIN-NFR-08 | Open; no acceptance asserted |
| P09 | Agent execution | AIN-BR-13, AIN-BR-14, AIN-NFR-08 | Open; no acceptance asserted |
| P10 | Mathematical optimization | AIN-BR-08 | Open; no acceptance asserted |
| P11 | Connected business workflows | AIN-BR-01 | Open; no acceptance asserted |
| P12 | Authentication | AIN-BR-02, AIN-NFR-01 | Open; no acceptance asserted |
| P13 | Authorization | AIN-BR-02, AIN-BR-11, AIN-BR-15, AIN-NFR-01 | Open; no acceptance asserted |
| P14 | Human approval controls | AIN-BR-09, AIN-BR-12, AIN-BR-15, AIN-NFR-08 | Open; no acceptance asserted |
| P15 | Protected audit | AIN-NFR-02 | Open; no acceptance asserted |
| P16 | Security and privacy | AIN-BR-12, AIN-NFR-01 | Open; no acceptance asserted |
| P17 | Production deployment | AIN-BR-17 | Open; no acceptance asserted |
| P18 | Monitoring | AIN-BR-16, AIN-NFR-05 | Open; no acceptance asserted |
| P19 | Backup and recovery | AIN-BR-17, AIN-BR-18, AIN-NFR-05 | Open; no acceptance asserted |
| P20 | Rollback | AIN-BR-18, AIN-NFR-05, AIN-NFR-07 | Open; no acceptance asserted |
| P21 | Performance and accessibility | AIN-NFR-04, AIN-NFR-06 | Open; no acceptance asserted |
| P22 | Integrated acceptance testing | AIN-NFR-02, AIN-NFR-03 | Open; no acceptance asserted |
| P23 | Operational documentation | AIN-BR-17, AIN-NFR-03, AIN-NFR-07 | Open; no acceptance asserted |
| P24 | Final scope acceptance | AIN-BR-01, AIN-BR-16 | Open; no acceptance asserted |

The existing [readiness catalog](../../infra/readiness.json) contains 24 requirements with production_accepted false. This matrix does not alter fingerprints, names, dependencies, records or acceptance. Research UAT success alone cannot close a production gate.

## 6. Coverage gaps requiring explicit follow-up

| Gap | Why the current links are insufficient | Required next evidence |
|---|---|---|
| Full route/role/resource authorisation | One owner/auth test cannot prove all handlers or future tenant boundaries | Maintained route/action matrix, negative cases and deployed identity review |
| Corpus and answer relevance | Exact quote/citation and scope checks do not prove semantic correctness | Frozen representative labeled cases, independent adjudication, refusals/misses and limitations |
| Real data/source governance | Import integrity does not approve purpose, licence or source truth | Accountable source-rights/steward review and source correction/lifecycle process |
| Performance and capacity | Queue caps and short local HTTP measurements are not workload acceptance | Agreed targets and error-inclusive representative authenticated/model/SQL concurrency tests |
| Accessibility and usability | Selected browser/layout receipts and header tests are incomplete | Keyboard, screen-reader and browser/device matrix with actual results |
| Recovery and key loss | Local supported restore is not independent computer-loss recovery | Off-site/escrow policy, agreed RPO/RTO and independent environment drill |
| Audit and privacy | Local records/checksums are not protected off-host evidence or retention | Defined access, privacy/retention/deletion and tamper-resistance review |
| External operational integration | Existing research source has no airline effect authority | Separate contract, data/action rights, sandbox and independent domain acceptance |
| Release assurance | A pinned source link is not a current build or deployed artifact | Exact revision/artifact configuration, hosted checks, deployment smoke and reviewed outcome |

The matrix deliberately retains these gaps rather than marking a requirement complete because an adjacent test exists.

## 7. Acceptance record template

The following is a **blank template**, not evidence. Keep private details out of public source.

```text
Requirement(s):
Journey / test(s):
Exact source revision:
Build / artifact identities:
Environment and dependency versions:
Fixture / authorised dataset / protocol identity:
Execution date and operator:
Actual execution mode (fixture / local model / recorded report / other):
Expected outcome:
Observed outcome:
Passed / failed / skipped / unavailable:
Sanitised evidence reference and integrity:
Defects / limitations:
Reviewer and authority:
Decision and scope:
Follow-up owner:
```

Do not invent names, approvals or passing artifacts. Record synthetic cases as synthetic, and do not let a self-review stand in for an independently authorised acceptance.

## 8. Maintenance and verification rules

1. Add or revise the originating BR/NFR before claiming a new capability satisfies it.
2. Link representative source and independently meaningful tests; identify uncovered clauses.
3. Pin new test/report results to the actual revision, environment and fixture/protocol.
4. Preserve negative results and old evidence; do not relabel previous experiment/deployment receipts as new.
5. Review changed contracts, model/corpus identities, state/migrations and role boundaries.
6. Update the relevant ADR, diagram, runbook and production relationship map.
7. Keep new requirement acceptance separate from research history and P01–P24 production acceptance.

### Checks performed for this change

- All 18 BR IDs and 8 NFR IDs match AIN-EA-02.
- Representative source/test/report paths exist in the reviewed repository tree.
- Named test identifiers/titles are present in the fetched test files; BR-01 uses an explicitly file-level entry.
- The catalog retains 24 open production gates.
- Markdown link targets were checked for existence.
- No test suite, browser journey, private database inspection, training, generation, restore or deployment was executed.

**Next planned document:** AIN-EA-11 — Operations and Recovery Plan, consolidating instance/startup, monitoring, incident, backup, restore, rollback and ownership procedures without replacing the detailed runbooks.
