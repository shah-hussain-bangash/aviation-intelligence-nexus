# Local schedule to UTC research decisions

Third new local data-platform increment, 24 November 2026. A standalone converter now supplies UTC queries to the availability-time weather join. The demonstration uses generated schedules and weather only. It does not change the historical importer, frozen model, dashboard, accounts or running deployment.

## Input and time policy

Call `pipelines.decision_times.decision_queries(flights, mappings, scope=..., lead_minutes=120)`. Each schedule has exactly `flight_id`, `flight_date`, `scheduled_departure`, `origin` and `source_scope`. Flight IDs must be unique. Dates use `YYYY-MM-DD`; clocks use four digits `HHMM`. `2400` means midnight on the following local calendar date, including month/year rollover. Invalid dates, clock values, extra fields and mixed scopes fail the entire call. There is no arrival-outcome input.

Airport mappings are explicit references keyed by the three-letter origin. Each has exactly `timezone`, `reference_id`, `source_scope`, `valid_from` and `valid_until`. Validity covers the **normalized local departure date**, start inclusive and end exclusive. Thus a `2400` departure requires a mapping valid on the following date. A missing or out-of-period reference excludes the schedule; the converter does not guess the timezone or fall back to the computer's timezone. This version supports one declared validity interval per origin per call; callers must partition separately governed mapping histories before processing different intervals.

Timezone rules always load from the installed `tzdata` package through `ZoneInfo.from_file`, using its actual bytes. The API dependency lock already pins this package. System timezone databases and Windows local settings are not used. Each mapped decision records the package version, timezone name, reference ID, validity interval and SHA-256 of the timezone file. The package version and hash make a conversion reproducible; they do not authenticate the airport-to-zone association or establish source authorization.

The converter round-trips both daylight-saving folds through UTC. No round-trip candidate means a nonexistent local civil time; two distinct candidates mean an ambiguous repeated local time. Both cases are excluded with no decision query. No fold is chosen silently and no nonexistent time is shifted automatically. An airline/provider timestamp or reviewed disambiguation policy is required before such a schedule could be included.

After finding one unambiguous departure instant, subtract the lead time **in UTC**, not in local civil time. Lead is an integer from zero to 1,440 minutes. This preserves elapsed minutes across a daylight-saving change. Date/time overflows are refused. A valid query contains only the existing weather join's `query_id`, `origin`, canonical UTC `decision_at` and `source_scope`.

## Trace and exclusions

The result has `decisions`, one per input schedule in order, and `queries`, only the ready subset. Status is one of:

| Status | Meaning |
| --- | --- |
| `ready` | One UTC departure and decision time derived from the explicit mapping |
| `excluded_missing_mapping` | No declared reference for this airport |
| `excluded_mapping_period` | Reference does not cover the normalized local departure date |
| `excluded_nonexistent_local_time` | Local time falls within a civil-time clock gap |
| `excluded_ambiguous_local_time` | Local time repeats with two possible UTC instants |

Excluded rows retain their schedule and any available mapping provenance, with null UTC decision fields. Errors in field structure or the supplied mapping table reject the whole call, including invalid unused mappings. A mapping name is restricted to packaged timezone resource names; external timezone paths are not accepted. Rules and labels are caller-declared research inputs, not confirmation that an airport or flight exists. Synthetic `AAA`/`BBB` examples merely illustrate Dubai and New York timezone rules.

There are at most 50,000 schedules and 2,000 mapping entries per call. Timezone resources are capped at 1 MiB each and cached by name within that call. Results remain in memory. These limits are admission bounds, not measured throughput, a hard deadline, representative big-data qualification or a streaming execution engine. Trusted input iterables must terminate; blocked generators are not interrupted. Historical use requires separately authorized mappings and schedules, with verified date/time semantics.

## Reproduce the integrated synthetic trace

```powershell
.\.venv\Scripts\python.exe -m pipelines.verify_decision_times
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_decision_times.py -v
npm.cmd test
```

The host-only command accepts no existing database, external input or output path. It creates a fresh case under `.local/decision-times/<case_id>/`, with `synthetic-input.json`, `joined-results.json` and `report.json`. It never overwrites a case. Reports record the case ID, source revision/dirty state where available, participating source hashes, exact input/result hashes, counts and thirteen checks. Source identity includes the reused import-drill identity helper's dependencies. Failed cases retain inputs and a fixed error code. These records establish local consistency, not signed provenance.

Seven schedules reconcile to three ready queries and four explicit exclusions. The ready queries all match synthetic weather. A Dubai-time example derives a 05:30 UTC decision for a 10:00 local departure with a 30-minute lead, and excludes a weather report available at 05:31. The trace also covers midnight rollover, spring/fall clock transitions, missing/expired mappings and retained timezone evidence. Unit tests additionally cover UTC lead subtraction across clock changes, mapping boundaries, invalid input, scope separation, bounded input and failure retention.

Real weather ingestion, trustworthy receipt times, independently reviewed airport/station mappings, representative resource measurements and an independent chronological model experiment remain open. Existing US flight records have not been assigned these generated references or enriched with weather. No predictive improvement, airline operational approval, phase completion or production readiness is claimed.
