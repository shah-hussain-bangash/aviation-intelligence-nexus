# Implementation roadmap

Keep all 64 workspace options. Prioritize one integrated, measurable workflow before expanding services.

The local-first [production delivery sequence](PRODUCTION_DELIVERY_PLAN.md) defines the exit evidence for these phases. Its first foundation increment is [request correlation and safe error telemetry](REQUEST_CORRELATION.md); this does not close a production acceptance requirement.

1. **Foundation:** Python API, persistent database, migrations, identity, permissions and correlated audit.
2. **Data:** authorized historical flight release, reproducible ingestion, schema/quality checks, time-safe joins and source coverage.
3. **Data science:** reproducible delay baseline, temporal holdout, calibration/error analysis, model artifact and versioned scoring.
4. **Integration:** show actual records, predictions, lineage and failures in the existing dashboard.
5. **Evidence and agents:** permitted document processing, evaluated retrieval/generation, bounded tools and durable human checkpoints.
6. **Optimization:** explicit formulation, computed candidates, independent feasibility verification and proposal-bound review.
7. **Release qualification:** deployed environment, security/integration/load/accessibility tests, monitoring, backups and demonstrated rollback/recovery.

Role-specific improvements: add explicit SQL/Pandas/NumPy evidence, a concrete clustering evaluation, a small LP/MIP example, a measured fine-tuning comparison where justified, and an actual Databricks workflow if access is available.

The local [import safety increment](IMPORT_SAFETY.md) adds private archive capture, transaction-bound replay and a synthetic lineage/concurrency drill. It is data-reliability progress, not source approval, representative throughput, completion of the foundation phase or production acceptance.

The [availability-time feature increment](TIME_SAFE_FEATURES.md) adds a bounded research join and synthetic delayed-weather demonstration. It does not integrate a weather feed into the frozen model or establish predictive improvement.

The [UTC decision-time increment](DECISION_TIMES.md) connects explicitly mapped synthetic local schedules to the availability-time join. It records timezone rule bytes and excludes unresolved civil-time ambiguity; it does not authorize real airport mappings or enrich the frozen flight dataset.

The [feature resource measurement increment](FEATURE_RESOURCE_MEASUREMENT.md) supplies deterministic synthetic smoke/capacity workloads and measured phase time/Python allocation evidence. It does not substitute for representative authorized data or whole-system load qualification.

The [resumable synthetic ingestion increment](RESUMABLE_SYNTHETIC_INGESTION.md) adds durable batch states, single-host worker exclusion and an actual crash/restart/replay trace. It does not authorize external imports or install a production scheduler.

The [retry scheduling increment](RETRY_SCHEDULING.md) adds opt-in persisted due times, bounded backoff and pause controls to synthetic case queues. It is manual invocation policy, not installed background supervision or real-source approval.

The [bounded ingestion runner](BOUNDED_INGESTION_RUNNER.md) executes synthetic due work in the foreground with cooperative stop/pause, invocation budgets and recorded status. It does not install a background supervisor or grant real-source approval.

The [runner snapshot inspection increment](RUNNER_STATUS_INSPECTION.md) classifies recent/stale records without liveness claims and retains an actual abrupt-runner-exit/ledger-replay trace. It is not independently supervised monitoring or an automatic recovery policy.

The [offline case reconciliation increment](CASE_RECONCILIATION.md) compares reconstructed retained batches with selected stored rows and queue/ledger bindings. It preserves source cases and rejects changed copies; it does not authenticate data or certify current service health.

The [point-in-time split preparation increment](TEMPORAL_PREPARATION.md) validates feature and label availability at chronological cutoffs, with targets separated from model inputs. It uses a synthetic demonstration and preserves the frozen experiments; it does not claim model benefit or close earlier phases.

The [train-only preprocessing increment](TRAIN_ONLY_PREPROCESSING.md) fits encoders/scaling only on prepared training features and freezes that state for future transformations. Its synthetic evidence is not a fitted predictive model or real-data improvement claim.

The [validation regression selection increment](VALIDATION_REGRESSION_SELECTION.md) records a local development protocol, fits train-only synthetic candidates and selects on validation MAE without test evaluation. It does not establish real-data model benefit or production acceptance.

The [one-attempt synthetic evaluation increment](SYNTHETIC_HOLDOUT_EVALUATION.md) pins a frozen selection under a separate policy and consumes a local marker before holdout reads. It does not refit candidates or establish globally protected evaluation or real airline model quality.

The [read-only synthetic error diagnostics](SYNTHETIC_ERROR_DIAGNOSTICS.md) reconcile a completed evaluation receipt with descriptive origin/category error reports. They never fit or select models and do not establish statistical significance, real airline quality or a fresh holdout.

The [portable synthetic model bundle](SYNTHETIC_MODEL_BUNDLE.md) exports receipt-bound frozen JSON scoring state and verifies prediction parity without training-data access. It is local artifact execution evidence, not a protected model registry or deployed service.

The [local synthetic model catalog](SYNTHETIC_MODEL_CATALOG.md) records verified artifact versions and revision-bound selection/previous-version rollback in separate private state. It does not deploy the selected version or establish protected model promotion.

The [catalog-selected scoring command](CATALOG_SELECTED_SCORING.md) binds local synthetic predictions to an observed selected version, revision and feature-file hash, with post-score change checks. This is CLI integration only; it does not add a scoring service or protected execution ledger.

The [opt-in authenticated synthetic scoring API](AUTHENTICATED_SYNTHETIC_SCORING.md) connects the selected-version workflow to existing local sessions/roles and server-configured dataset IDs. It is disabled by default and verified in-process; frontend routing, deployment and production identity remain open.

The [Synthetic Model Lab dashboard connection](SYNTHETIC_SCORING_DASHBOARD.md) adds a role-aware panel and exact proxy routes with bound result rendering and stale-result clearing. It is checked in an isolated fixture-session browser harness, not a deployed authenticated browser journey.

The [isolated browser session rehearsal](ISOLATED_BROWSER_SESSION.md) adds a native-test-only cookie namespace and verifies ordinary browser login/scoring/viewer/logout with disposable accounts. It does not qualify the user's real-account journey or deployed release; the auth source fingerprint requires fresh future recovery evidence.

The [versioned synthetic recovery runbooks](RECOVERY_RUNBOOKS.md) replace private workstation launchers with explicit image/revision inputs, isolated admission and reviewed HTTP, outage, restart, restore and encrypted continuation commands. Earlier private observations do not qualify the refactored runners; retain new execution evidence before release review.

The [historical model recovery parity command](RESEARCH_MODEL_RECOVERY.md) copies an explicitly trusted, manifest-pinned model pair into a synthetic schema-8 recovery state and compares three predictions before/after restore. It never opens the original flight database or establishes new model accuracy, full-system recovery or production acceptance.

Every milestone needs executable code, observed test results, documented limitations and a reproducible demo. Planning targets and synthetic outcomes must not be presented as measured airline improvements.
