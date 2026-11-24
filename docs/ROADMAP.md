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

Every milestone needs executable code, observed test results, documented limitations and a reproducible demo. Planning targets and synthetic outcomes must not be presented as measured airline improvements.
