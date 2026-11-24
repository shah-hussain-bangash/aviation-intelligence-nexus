# Synthetic feature-pipeline resource measurement

Fourth new local data-platform increment, 24 November 2026. A repeatable host-only measurement now exercises the combined schedule-to-UTC and availability-time weather path. It generates synthetic records in memory and never reads an existing application database, downloads data, trains a model or starts a service.

## Fixed workloads

```powershell
.\.venv\Scripts\python.exe -m pipelines.measure_feature_pipeline
.\.venv\Scripts\python.exe -m pipelines.measure_feature_pipeline --scale capacity
```

| Scale | Synthetic schedules / queries | Synthetic weather events |
| --- | ---: | ---: |
| `smoke` (default; included in tests) | 500 | 2,000 |
| `capacity` (explicit local measurement) | 50,000 | 200,000 |

The larger workload reaches the current admitted schedule/query/event counts of the two libraries. Reaching those limits is a measured synthetic workload, not representative airline volume, whole-system capacity or a big-data architecture qualification. The benchmark does not exercise the 2,000-entry timezone-mapping limit; both workloads use four declared synthetic airport mappings.

Schedules start on 1 January 2025 and advance one local minute per record, rotating four synthetic airport codes. They use explicit UTC, Dubai, New York and Perth timezone references. The largest workload remains in January/early February, so it is not a daylight-saving stress test; the existing decision-time tests cover clock gaps, repeated times and midnight rollover. Weather begins two days earlier, with a deterministic interval sized to cover the workload and a 90-second declared receipt lag. No real airport or weather observations are represented.

All schedules should produce ready UTC decisions, and all queries should match weather no older than the existing one-hour threshold. Counts and labels reconcile across the generated schedules, UTC decisions and joined features. An independent linear scan checks eight selected query results, including each airport and positions across the input. This is sampled selection/value verification, not an independent oracle for every output. Existing focused tests cover exclusions and future-information leakage.

## What is measured

Each run records elapsed and process CPU seconds for generation, UTC conversion, weather joining and verification. A one-frame Python `tracemalloc` tracker runs across those phases and records peak/current traced allocation bytes. Verification includes canonical record hashing and the independent scans. Instrumentation and verification costs are included in the overall measured time. Preflight/Git identity, initial recipe writing, imports and final report serialization/writing are outside the timed pipeline.

Traced Python allocations are **not whole-process memory**, RSS, system peak working set or GPU memory. Native allocations and tracker overhead can differ from the traced figure. The tracker itself slows execution. Values are one local observation under the current machine load, not a throughput guarantee or a production service objective. Tests verify measurements and accounting exist; they do not assert an arbitrary timing threshold. Run the capacity command separately from other local tests when collecting a baseline.

Inputs and results are retained through a deterministic recipe and hashes of canonical UTF-8 JSON record streams (sorted keys, compact separators, one newline per record). The large in-memory datasets are not written to disk. Reproduction requires the same recipe, generation code, timezone package bytes and software environment; stream hashes verify reproduced records, not source authenticity. Timezone byte hashes, Python/tzdata versions, source hashes and available Git revision/dirty status are recorded. No hostname, account name, hardware inventory or raw external data is collected.

## Retained evidence and safety boundary

The command accepts only the two fixed scales, with no database/input/output argument. It creates a new case under `.local/feature-measurements/<case_id>/`, retaining `recipe.json`, `started.json` and `report.json`. Existing cases and redirected paths are refused. Container/agent-job/monitor execution is refused. It is an explicit OS-owner research command, not a new web permission path or background scheduler.

Failure retains a fixed error code, stage, recipe and measurements where possible. The command refuses to run if another Python allocation tracker is already active, and stops only the tracker it starts. Bounds limit admitted record counts, but there is no hard CPU, memory or I/O deadline; trusted generators must terminate. A killed process may retain only the starting report. The capacity run can use substantially more actual process memory than its traced allocation value, so it should not run unattended alongside competing jobs.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_feature_measurement.py -v
npm.cmd test
```

Production still needs representative authorized data, actual receipt-time and mapping evidence, whole-process/container resource measurement, repeated workload/load tests, defined service objectives and final-image qualification. These measurements do not establish model benefit, complete ingestion scheduling, cloud readiness or production acceptance. Frozen model reports, historical data, dashboard behavior and primary deployment remain unchanged.
