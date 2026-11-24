# Availability-time research features

Second new local data-platform increment, 24 November 2026. This is a standalone research join and a synthetic demonstration. It does not attach weather to the frozen delay model, change predictions or import an external weather feed. The running dashboard and its historical evidence remain unchanged.

## Decision rule

`pipelines.time_safe_features.weather_features(queries, events, scope=..., max_age_seconds=3600)` returns one result per research query in its input order. A query supplies a unique ID, origin airport, decision timestamp and explicit source scope. An event supplies an ID, airport, observation timestamp, recorded availability timestamp, temperature in Celsius, wind in knots and matching scope. Extra fields, including target/outcome fields, are rejected.

For each airport, select the event with the greatest `available_at` **at or before** `decision_at`. The exact availability boundary is inclusive. Observation time must be no later than availability time, so the selected observation is also no later than the decision. A weather observation collected before departure but received afterward cannot enter that earlier prediction.

Availability must mean the time the research system could actually consume the information, including publication and ingestion delay. A source observation timestamp alone cannot supply this evidence. Caller-supplied timestamps and labels are validated structurally, not authenticated; a falsely early availability declaration can still cause leakage. This is a required input contract, not proof of source truth.

All timestamps use canonical UTC `YYYY-MM-DDTHH:MM:SSZ` and are parsed as timezone-aware UTC. Local schedule times, offsets, fractional seconds and naive timestamps are refused. Airport timezone/DST conversion and interpreting scheduled `2400` remain upstream responsibilities; the importer does not acquire a UTC decision time through this change.

Age is measured from observation time to decision time. Ages up to the chosen maximum are allowed; older observations return `stale` with null feature values and retained event/time provenance. No candidate returns `unavailable` with null provenance/features. Zero temperature or wind remains a valid measurement, distinct from missing values. A stale most-recently-available event does not silently fall back to an earlier event. This latest-availability policy must be reviewed before adopting different source revision semantics.

Identical repeated event IDs collapse; conflicting payloads for one ID fail the whole call. Two distinct events at the same airport and availability timestamp are ambiguous and refused. A feed adapter must resolve that ambiguity through an approved revision policy, rather than depending on input order. Query IDs must be unique. The complete event input is validated even if some events fall after every query; invalid future input can reject a batch, but valid later information cannot change an earlier selected feature.

## Scope and bounds

Both query and event labels must match the explicitly requested `synthetic` or `historical_research` scope. Labels do not establish rights or operational authority. The demonstration creates only synthetic records and never selects an existing database. Using the library on historical research requires separately authorized sources and justified availability evidence.

Temperature and wind must be finite numeric values; negative wind is rejected. These are representation checks, not meteorological quality certification. Source units, plausible ranges and station-to-airport mappings still require validation.

At most 200,000 input events and 50,000 queries are accepted per call, including duplicate inputs. Maximum observation age is an integer from 1 to 86,400 seconds. Events are grouped and sorted once; binary search selects each query's event. Memory retains bounded input copies and results. This is not a streaming big-data engine, a measured capacity claim or a hard execution deadline. Input iterables must be finite and supplied by trusted local research code; a blocked iterator is not interrupted. No SQL, arbitrary path, network request or target column is accepted by the join.

## Reproduce the synthetic case

```powershell
.\.venv\Scripts\python.exe -m pipelines.verify_time_safe_features
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_time_safe_features.py -v
npm.cmd test
```

The host-only command accepts no archive/database/output arguments. It creates a new case under `.local/time-safe-features/<random-id>/`, retaining `synthetic-input.json`, `joined-results.json` and `report.json`. Existing cases are never overwritten. Reports bind the exact input/result bytes, participating source files and available Git identity. Source identity also includes the reused import-drill identity helper's dependencies. These are local consistency records, not signed provenance.

Seven synthetic queries yield four matches, one stale result and two unavailable results. Ten demonstration checks cover publication boundaries, a delayed report, future-event noninterference, airport isolation, labels and source stability. Unit tests additionally compare 300 generated queries against an independent candidate scan and reject conflicting revisions, mixed scopes, malformed times, target fields and bounded-input violations. Failed cases retain their inputs and a fixed error code; no external data, model training, service startup or deployment occurs.

Next integration requires an authorized weather adapter with measured receipt times, audited station/UTC mappings, representative volume/resource tests, and a new chronological experiment independent of the already-used test holdout. This increment does not establish predictive benefit, production acceptance or completion of the data-platform phase.
