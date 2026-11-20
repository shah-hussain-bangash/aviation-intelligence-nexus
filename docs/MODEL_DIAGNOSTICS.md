# Recorded model diagnostics

The signed-in dashboard offers **Inspect model quality**. Select April validation or May test, and optionally a May reporting carrier. All authenticated roles can inspect these public aggregates. This is a read-only explanation of the existing delay-v2 experiment; no inference, model fitting, threshold tuning or database scan occurs.

## Evidence and method

`GET /api/v1/research/model-diagnostics` reads only `docs/reports/Delay_v2.json`. A pinned SHA-256 over UTF-8/LF text rejects missing, changed or oversized evidence. It validates confusion counts, derived prevalence/accuracy/precision/recall/F1, calibration populations and observed frequencies, and carrier count/outcome reconciliation. Failure returns a safe HTTP 503 without scores. Anonymous access is denied; the fixed dashboard proxy allows only GET. This is source integrity, not protected auditing or independent model qualification.

The diagram plots each recorded bin's mean probability against observed frequency, with a perfect-agreement reference. Exact values and counts are available in a table. Binned ECE is `sum(count * abs(mean_probability - observed_rate)) / records`; it depends on bins and population. Empty bins are omitted and points use equal sizes. No confidence interval, hypothesis test, new holdout, carrier fairness/ranking, causal interpretation or live drift monitoring is inferred.

April has 577,730 eligible observations, May 597,574. April binned ECE is 0.0122176069; May is 0.0409413971. May ROC-AUC is 0.6506087793. At the fixed April-selected 0.17 threshold, May contains 241,732 false alerts, 36,371 missed delays and 104,667 true alerts. Same-period all-carrier Brier/log-loss comparisons use the constant training prior; no per-carrier prior comparison is supplied. Carrier populations have different traffic mixes. These historical observations do not demonstrate an intervention benefit.

## Interaction and verification

Period selection resets the carrier to all when April is selected. Cohort JSON export includes the selected metrics, fixed threshold, report fingerprint, method, limitations and research boundary. Refresh hides old results while loading. Invalid/unavailable evidence clears scores and disables export; recovery permits a fresh fetch. Sign-out invalidates in-flight responses and clears displayed metrics, carrier choices and export state. No account or raw flight records appear in the export.

The full Windows suite passes 203 tests (164 Python, 39 Node); Linux skips the Windows DPAPI provider case. New cases cover report tampering/line endings, inconsistent counts/rates/bins, read-only viewer access, safe failure responses, proxy scoping, rendering, invalid cohorts and escaped text. An isolated headless-browser preview uses the real component/styles and recorded response, with synthetic transport and no real user session. Desktop 1280 and mobile 390 pixels, carrier/period changes, selected export, outage/recovery, sign-out and late responses passed. Screenshots were inspected. See `reports/Model_Diagnostics_Dashboard.json`.

Run `npm test` for the suite. The published evaluation report is unchanged; May must not be reused for model selection. The panel verifies recorded evidence, not the currently deployed artifact's health. Deployment health remains in the separate monitoring panel. Existing rollback manifests require their existing compatibility checks; no new rollback qualification is claimed. All 24 production requirements remain open.
