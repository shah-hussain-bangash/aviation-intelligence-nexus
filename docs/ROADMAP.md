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

Every milestone needs executable code, observed test results, documented limitations and a reproducible demo. Planning targets and synthetic outcomes must not be presented as measured airline improvements.
