# Historical route delay-pattern segmentation

This offline data science experiment adds unsupervised clustering to the existing delay-classification work. It groups US domestic directional routes, combining reporting carriers, by observed delay and cancellation patterns. It does not predict future route risk, rank airlines, explain causes, optimize operations or establish UAE airline suitability. No dashboard prediction model or account is replaced.

## Reproduce

From the repository root, after importing the official BTS January–May 2025 data:

```powershell
.\.venv\Scripts\python.exe -m ml.route_segments --database .local/ain.sqlite3 --output .local/models/route-segments-new
```

Use a new output directory. The tool reserves it before reading the data and refuses an existing directory, including a failed prior run. It never imports or migrates the database: the SQLite connection is read-only with `query_only` enabled and a consistent read transaction. SQL processing is interrupted if its progress checks exceed 120 seconds. It loads route aggregates into Pandas rather than materializing every flight in memory. NumPy, Scikit-learn and two numerical-library threads perform the clustering. This is local batch processing, not distributed Spark/Databricks execution.

The private output contains the fitted scaler/KMeans model, cluster-ID mapping, aggregate route assignments, a frozen-protocol receipt and the result report. Model artifacts, route CSVs, raw data and the database remain excluded from Git. Only the reviewed aggregate report and this runbook are published. Joblib files must remain locally trusted; this is not an upload/inference service.

## Fixed protocol and features

`ml/route_segments_v1.json` is checked against its canonical UTF-8/LF SHA-256 before execution. A change requires a new experiment version. January–March supply training route aggregates; May supplies a retrospective later-period comparison. April is excluded. May outcomes were already available in earlier classification experiments, so this is not a newly untouched holdout or an independent confirmation of generalization.

Rows must belong to `BTS_REPORTING_CARRIER`. Origin/destination order matters. Completed observations require cancellation and diversion flags both zero and an observed arrival delay. Cancellation/diversion flags must be valid. Training routes require at least 200 completed observations; comparison routes require at least 50. Their flight coverage and excluded route counts are explicit in the report.

Each route has four features:

| Feature | Definition |
| --- | --- |
| `delay_15_rate` | Fraction of completed observed arrivals delayed at least 15 minutes |
| `delay_60_rate` | Fraction of completed observed arrivals delayed at least 60 minutes |
| `mean_positive_delay_capped_180` | Mean arrival delay after clipping each completed observation to 0–180 minutes |
| `cancellation_rate` | Cancelled flights divided by all source flights on the route |

The first three denominators exclude cancellations, diversions and missing arrival observations. Cancellation uses all route flights. Clipping limits the influence of extreme minutes and is part of the fixed definition, not data cleaning tuned after seeing results. Route profiles report unweighted mean route features; they are not passenger-weighted or flight-weighted business KPIs.

`StandardScaler` is fitted only on supported training routes. KMeans candidates use k=2–6, seed 42 and 20 initializations. Selection maximizes sampled training silhouette among candidates with at least ten routes and at least 1% of training routes in every cluster; lower k breaks ties. Silhouette sampling uses at most 2,000 training routes and a fixed seed. If no candidate satisfies support, execution fails rather than inventing a usable segmentation.

Training-only refits with seeds 0, 7, 21 and 84 measure agreement with the selected fit using adjusted Rand index. This tests initialization sensitivity, not bootstrap or external stability. The frozen training scaler/model then assigns the supported May route feature vectors. The report shows cohort coverage, unsupported/unseen routes, same-route cluster transitions and feature shifts in training standard-deviation units. Those shifts mix route composition and behavioral changes; the overlap transition table isolates shared route identities but does not identify causes.

Cluster display IDs are sorted by training mean delay-15 rate. IDs are descriptive group labels, not risk thresholds, business actions or a calibrated ranking. KMeans operates on correlated standardized features, so their geometry and implicit weights affect the result.

## Observed real-data result

On 20 November 2026, new experiment code based on commit `b5a570138be2744788b1a75d534b7f3264bd9b70` ran against the local 2,835,101-record BTS database in the normal Windows session. The actual SQL/fit/report execution took 43.696 seconds on that workstation. This is one local runtime observation, not a resource or scale qualification.

| Coverage | January-March training | May comparison |
| --- | ---: | ---: |
| Official flights observed | 1,645,503 | 605,648 |
| Completed observed arrivals | 1,611,046 | 597,574 |
| Directional routes observed | 5,914 | 5,928 |
| Routes meeting support threshold | 2,488 | 3,357 |
| Flights on supported routes | 1,357,273 | 552,262 |

The 583,950 April rows are outside this experiment. The route support rules exclude 3,426 observed training routes and 2,571 observed May routes from fitting/comparison respectively. All five candidates satisfied their training support constraints; k=2 had the highest sampled training silhouette, **0.452883**. All four alternate training seeds had adjusted Rand index **1.0** against the selected assignment. This is observed initialization agreement, not a general stability guarantee.

| Training group | Routes | Mean route delay >=15 rate | Mean route delay >=60 rate | Mean route capped positive delay | Mean route cancellation rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 1,705 | 16.72% | 5.35% | 10.45 minutes | 1.46% |
| 1 | 783 | 26.10% | 10.54% | 18.32 minutes | 3.23% |

Among the **2,447 routes supported in both periods**, 875 (**35.758%**) changed assignment when the frozen model was applied to May outcomes. Another 910 supported May routes were absent from the supported training cohort; the report's `evaluation_supported_routes_unseen_in_training` field means absent from that fitted cohort, not necessarily never observed as a sparse route in January-March. Forty-one supported training routes were absent from the supported May cohort.

The transition matrix (training groups as rows, May groups as columns) is `[[1006, 684], [191, 566]]`. May outcome groups therefore do not provide permanent route labels. Seasonal/cohort effects, sampling variation and actual outcome changes can all contribute; this analysis does not separate them. No alarm threshold or operational action was accepted.

The complete aggregate evidence is [Route_Segments_v1.json](reports/Route_Segments_v1.json). The artifact SHA-256 and source archive hashes are recorded there; only the private output contains the actual model and route assignments. Regression tests use synthetic data and do not need these private files. The full Windows suite has 169 tests (142 Python, 27 Node); Linux skips the Windows-only DPAPI provider case.

## Interpretation and acceptance limits

Silhouette is a separation diagnostic, not classification accuracy. Its geometry favors compact, convex groups; a high score does not demonstrate useful aviation segments. See the official [Scikit-learn clustering guide](https://scikit-learn.org/stable/modules/clustering.html#silhouette-coefficient) and [silhouette definition](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html). No semantic ground-truth labels, stakeholder usefulness acceptance, external seasonal validation, bootstrap stability, causal benefit or cost savings are claimed.

Five regression tests cover frozen-protocol integrity, SQL source/date/direction/denominator rules, invalid status rejection, temporal mutation, degenerate candidate rejection and existing-output preservation. In the temporal test, changing only later outcomes leaves the training scaler, candidate scores, selection and seed agreement unchanged while changing the later-period diagnostics. The test also verifies database bytes remain unchanged.

This is an offline research capability. Dashboard integration, interactive route exploration, scheduled segmentation refresh/drift alerts, UAE validation and production acceptance remain future work. All 24 production requirements remain open.
