# One-attempt synthetic holdout evaluation

Fourth new data-science continuation increment, 25 November 2026. A separate local evaluation policy can now score one already-selected synthetic regressor on generated chronological holdout rows. It does not fit/refit candidates, compare their test scores, change the validation-selected choice, touch the original historical May holdout or deploy a model.

## Separate policy and input freeze

The earlier validation-selection protocol remains unchanged: its selection function accepts no test rows and performs no test evaluation. The new `ain-synthetic-holdout-policy-v1` is an explicit **subsequent evaluation-stage** policy, limited to synthetic scope. It pins exact bytes of `registered-protocol.json`, `frozen-selection.json`, `holdout-features.json` and `holdout-labels.json`. It does not grant access to historical/restricted holdouts or override their policy.

Before any holdout file is opened, the evaluator validates the supported selection protocol, selected candidate/validation ordering, coefficient/layout and preprocessing hashes, finite parameters and the expected frozen artifact bytes. It uses JSON state only, not pickle/joblib or executable model deserialization. The feature layout must match the supported training-origin one-hot block followed by temperature/wind scaling. Unknown origins follow the recorded all-zero one-hot policy and are counted.

The demonstration finishes and freezes development selection before generating its synthetic test examples. It then records the evaluation policy before writing the two holdout files. This is an executed local sequence, not a protected independent registry or proof that a human/data generator was statistically blind to the toy formula.

## One local attempt, including failures

`ml.evaluate_synthetic_holdout.evaluate_once(experiment)` creates `holdout-attempt.json` with exclusive file creation **before** opening features or labels. Concurrent calls cannot both create that local marker. A malformed or partly written marker still prevents another attempt; there is no timeout, automatic deletion or reset. A separate existing result file also prevents admission. Tests exercise both threads and separate CLI processes competing for one claim.

Admission failure before a claim does not consume a new attempt or open holdout data. After a claim, changed/missing/bad holdout data or temporal/cohort validation failure consumes it. Fixing a failed attempt and rerunning is not done automatically. Review retained artifacts. Process exit, IO failure or power loss can leave an attempt without a complete receipt; the marker is deliberately retained. File close/exclusive creation is not a demonstrated power-loss durability/fsync guarantee.

This is **one attempt per local directory**, not globally exactly-once evaluation. An OS owner can edit/delete files, forge policy, copy a directory or create another case. Hashes and markers are not authenticated authorization or protection against such an owner. Protected holdout access, registry uniqueness, retention and independent approval remain production requirements.

## Scoring contract

The entire holdout must contain 2–10,000 matched feature rows with one unique label per query. The frozen `synthetic-development.json` must match the selection's canonical development hash and contain no test rows. Its training/validation query IDs cannot reappear in holdout; training IDs also bind to fitted preprocessing state. ID disjointness does not independently establish distinct physical flights or groups. No post-hoc missing/stale/maturity exclusions are performed. Decision times must lie in `[validation_end, test_end)`, weather must have been available by each decision, and labels must become available after decision but no later than `test_end`. Extra label fields, duplicates, orphans, unmatched weather and invalid numerical values refuse the claimed attempt.

Each JSON artifact is limited to 8 MiB. Reads reject duplicate keys/nonfinite constants and observably changed files. Frozen fields and file identities are rechecked after scoring. These are bounded local consistency checks, not a hard execution deadline, a general hostile-file sandbox, representative capacity measurement or authenticated source validation.

The evaluator reconstructs only the supported frozen preprocessing transformation into a CSR matrix, predicts with the recorded selected coefficient vector/intercept, and compares MAE/RMSE with the frozen training-median baseline. No `.fit` call occurs. One selected regressor and its fixed baseline are scored; candidate selection remains based on validation. Results include cohort size, unknown-origin count, input/state hashes and a prediction hash, without publishing raw test targets or per-row outcomes.

The selected artifact's historical `test_evaluated=false` describes its earlier selection stage and is never edited. A separate `holdout-evaluation.json` records the later evaluation state and `test_evaluated=true` only after metrics compute and frozen inputs still match. Failed results can retain a consumed attempt. Receipt-write failure also retains the marker. Repeated calls return refusal without reopening holdout data or overwriting the original receipt.

## Reproduce the synthetic workflow

```powershell
.\.venv\Scripts\python.exe -m ml.verify_synthetic_evaluation
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_synthetic_evaluation.py -v
npm.cmd test
```

The host-only demonstration accepts no existing case/database path. It creates `.local/synthetic-evaluation/<case_id>/`, registers/fits a new synthetic development selection, creates eight August toy-formula holdout rows under the separate policy, evaluates once, and verifies a second call is refused. Original experiment sources, real historical data, used holdout, API/dashboard and deployment remain unchanged.

Ten demonstration checks bind the development result, selection pins, retained claim, complete eight-row scoring, no refit, repeat refusal and unchanged receipts/inputs. Focused tests inspect marker-before-read ordering, refused repeat reads, post-claim failure consumption, frozen-selection mismatch, thread/process races, temporal cohort validation and CLI exit behavior.

The generated holdout uses a known deterministic toy formula related to the development generator. Its scores demonstrate execution and boundary mechanics; they are not independent airline accuracy, generalization evidence or proof of business improvement. Real data approval, statistically appropriate independent evaluation, protected experiment/holdout services, representative model/load tests and production acceptance remain open.
