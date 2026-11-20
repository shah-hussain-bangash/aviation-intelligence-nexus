# Frozen-model input reliance

Select **Explore model inputs** on the signed-in dashboard. The panel explains a recorded grouped permutation experiment for delay-v2. It is a global performance diagnostic for one fixed April sample, not causality, an individual flight explanation, SHAP, feature selection, a new holdout evaluation or operational approval.

## Fixed experiment

The protocol was written before reading the diagnostic sample: `ml/importance_protocol.json`, canonical UTF-8/LF SHA-256 `3b1b1da7d092a05007a77a2864e1ab4c52bf669db610cba83098e1cf7788d04c`. It fixes April validation, seed 20261120, a uniform 10,000-row sample without replacement and three row permutations per group. The selected indices remain in source order. Groups are carrier, origin, destination, scheduled departure time and weekday. Hour and minute move together; the existing frozen pipeline recomputes sine/cosine pairs. The same three permutations are used for every group. Model, threshold, preprocessing and original experiment reports are preserved. No May outcomes are analyzed and no model is fitted.

`ml.permutation` verifies the public frozen-model report, trusted artifact hash and exact April CSV hash/count before scoring. It never opens the training or May CSV. It reserves a new private output directory, preserves failures and refuses replacement. A final check verifies artifact and April input bytes remain unchanged. Output includes sample-key/protocol/source fingerprints, the baseline, every shuffle result, mean and sample standard deviation. Raw rows, probabilities, serialized models and private state stay out of Git. Only the known locally created artifact is deserialized with joblib; this is not an arbitrary uploaded-model service.

The original dataset directory was inaccessible in this session. An operator-only read-only query reconstructed April from the deployed historical database using the original eligibility/order/CSV rules. The resulting validation CSV matched the frozen byte hash `2dc8e38595d10b664ef19de6b6b73aa63f8b7a90893cedef4797e271d702c3c5` exactly. A private copy of the deployed model matched its original artifact hash. No source ownership/permissions, database rows, credentials or active artifact were changed. The first attempt stopped at the inaccessible manifest before sample analysis. The final implementation verifies the pinned split hash directly, without trusting a mutable private manifest.

## Observed results

The April population has 577,730 eligible observations. The sampled baseline is log loss 0.4657917383, ROC-AUC 0.6494541539 and Brier 0.1479222997; these are subset metrics and must not replace the full-April evaluation. Mean log-loss increases after shuffling are:

| Group | Mean increase | Repeat sample SD |
| --- | ---: | ---: |
| Scheduled departure time | 0.02728768 | 0.00172815 |
| Origin | 0.00658523 | 0.00109499 |
| Carrier | 0.00510750 | 0.00061970 |
| Weekday | 0.00446558 | 0.00106096 |
| Destination | 0.00413169 | 0.00083260 |

Departure time had the largest measured reliance in this sample. This does not show it causes delays or remains most important in other periods. Correlated inputs may share/mask importance, and shuffling can create implausible routes/schedules. Repeat SD measures shuffle variation conditional on this fixed sample, not sampling uncertainty or a confidence interval. Negative importance remains supported and visible. No significance, stability across seasons, UAE transfer or business impact is inferred.

The source CLI completed in 1.466 seconds after verified input preparation; a second source run took 1.247 seconds and reproduced the exact sample fingerprint, baseline, all 15 shuffle results and summaries. Both private receipts are retained. These local timings are not capacity qualification. The aggregate result is `reports/Delay_v2_Permutation.json`; it is frozen and fingerprint-pinned by the API.

## Dashboard and API

`GET /api/v1/research/model-explanations` allows signed-in viewers, researchers and administrators to read the public aggregate. It loads a single size-bounded, pinned report, validates source/period/group contracts and recomputes mean/SD checks. It performs no flight SQL, artifact loading, inference or training. Missing/altered evidence returns safe HTTP 503 without explanations; anonymous requests receive 401. The dashboard proxy permits only the fixed read route.

The UI switches log-loss increase, ROC-AUC decrease and Brier increase, ranking groups within the chosen metric. Diverging bars retain negative values, a common symmetric scale and exact signed numbers. The full repeat table and limitations are available. JSON export preserves the complete report and names the displayed metric. Refresh clears old evidence before loading; failures disable export and metric switching. Sign-out clears results and invalidates late responses. Recorded file integrity is not protected auditing, independent acceptance or current artifact health.

## Reproduce and verify

With the original private April dataset and locally created trusted model available:

```powershell
.\.venv\Scripts\python.exe -m ml.permutation --output .local/experiments/new-april-reliance-check
```

Use `--dataset` and `--model` to select verified private copies if needed. The dataset directory must contain `validation.csv` with the exact frozen bytes. Use a new output directory every time. Do not tune on these diagnostics and then describe the original May scores as a fresh independent evaluation; future model selection needs a new validation/test design.

The complete Windows suite passes 213 tests (171 Python, 42 Node); Linux skips the Windows DPAPI provider case. New tests cover deterministic frozen-model reliance, paired time shuffling, unchanged input, invalid probability/groups, source/protocol/output guards before deserialization, report tampering/line endings, scope/summary checks, negative importance, auth/roles, safe failure, rendering, export scope and fixed proxy behavior.

An isolated headless-browser component preview used real assets and recorded experiment values through synthetic transport, without a real user session. Desktop 1280 and mobile 390 pixels, all three measures, repeat table, JSON export, outage/recovery and sign-out/late responses passed. Screenshots were inspected. See `reports/Permutation_Dashboard.json`. These checks do not qualify full accessibility, real-user browser authentication, production scaling or airline use. All 24 production requirements remain open.
