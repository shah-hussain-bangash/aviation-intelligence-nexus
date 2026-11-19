# Delay baseline v1: measured research result

Status: **trained locally; rejected for operational serving**. This is a completed modelling experiment, not a deployment milestone. The full measured report is `docs/reports/Delay_Baseline_v1.json`. The trusted serialized pipeline stays in `.local/models/delay-baseline-v1/model.joblib`, outside Git.

## Protocol

Fit all preprocessing and two logistic regression candidates (C=0.1 and C=1.0) on 522,269 January flights. Select C by February log loss; C=0.1 was selected. Choose a demonstration classification threshold using February F1 on the fixed 0.10–0.60 grid. The selected threshold is 0.15; this is not a business-cost or operational-capacity threshold. Freeze the candidate before opening March labels. The model was then evaluated on 592,301 March flights once. No model was retuned after viewing March.

Input columns are the explicit schedule/calendar allowlist in `MODEL_DATASET.md`. String-valued one-hot encoding groups categories with fewer than 20 training observations; unseen categories are ignored. The encoder is fitted on January only. Dataset hashes, record counts and temporal coverage are checked before training/evaluation. Convergence warnings fail the experiment. The saved pipeline's predictions were verified against predictions before serialization. Never load model files from untrusted sources.

## Results

| March metric | Logistic model | Constant January delay probability |
|---|---:|---:|
| ROC-AUC, higher is better | 0.5604 | 0.5000 |
| Average precision, higher is better | 0.2295 | 0.1959 |
| Log loss, lower is better | 0.5485 | 0.4949 |
| Brier score, lower is better | 0.1829 | 0.1576 |

At threshold 0.15, model precision is 20.76%, recall 89.89% and accuracy 30.81%. It raises 398,053 false alarms against 104,298 correctly flagged delays. Predicting every flight on time would give 80.41% accuracy, which illustrates why accuracy alone is inadequate. February probability quality was also worse than the constant-prior comparator (log loss 0.5676 versus 0.5121).

Ranking is slightly better than the constant baseline, but probability quality is worse and the threshold creates too many alerts. **Do not serve this candidate as an actionable risk model.** The report includes calibration bins and carrier slices. It does not establish statistical significance, prospective reliability, airline business benefit or UAE transfer. Release assessment was added retrospectively and is labelled accordingly.

## Reproduce and improve

```powershell
.\.venv\Scripts\python.exe -m pip install -r services/api/requirements-lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ml.train_baseline
```

The default model directory is protected from overwrite. Do not rerun against the same March holdout while iterating. For a fresh experiment, preregister a new temporal contract using longer training history and an untouched later test month, improve schedule/calendar representation, and compare a stronger model with the constant baseline. Investigate drift and calibration using training/validation only. The current training script intentionally implements the fixed Q1 contract; change code and dataset version explicitly for the next experiment.

Dependencies are pinned directly in `requirements.txt`, with an environment snapshot in `services/api/requirements-lock.txt`. The snapshot was tested on Windows/Python 3.14; it is not a cross-platform, hash-verified lock. Backend endpoints report the verified artifact as research-only and expose its report; they do not serve predictions. Restart the API after source updates to load those endpoints.

Method references: [scikit-learn one-hot encoding](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder), [probability calibration](https://scikit-learn.org/stable/modules/calibration.html), [log loss](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.log_loss.html).
