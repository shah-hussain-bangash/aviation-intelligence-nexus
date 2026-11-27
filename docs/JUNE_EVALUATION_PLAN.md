# Frozen June evaluation plan

The existing delay-v2 model trained on January–March 2025, selected its settings and demonstration threshold in April, and evaluated May. Those months are already used. The next planned comparison is June 2025, strictly later than the registered model periods. This does **not** establish that no person or other experiment has previously inspected June.

`ml/june_evaluation_plan.json` prespecifies the target/cohort, frozen-model inference, constant training-prior baseline, metrics, research comparison, carrier/origin diagnostics and a day-cluster bootstrap design for loss differences. The bootstrap is a plan, not implemented or executed statistical evidence. Historical schedule snapshots and US-to-UAE transfer limitations remain. No calibration, refitting, model selection or threshold search is permitted in this comparison.

From the native research checkout, prepare a fresh private snapshot using the existing trusted model's explicit artifact fingerprint:

```powershell
.\.venv\Scripts\python.exe -m ml.register_evaluation .local/june-plan-NEW --model-sha256 71b23232edc615a01daee387e1e7dbb2c0aa3f7dae2b4d1f33fabbc0fbbff732
```

The registrar validates the frozen plan fingerprint, copies only the registered local delay-v2 artifact/report through the existing trusted-copy helper, checks the recorded period groups, and freezes the report's numeric threshold and training prevalence. It never deserializes a model or accepts/opens a candidate archive. It checks the original source bytes and writes `plan.json`, `model/model.joblib`, `model/report.json` and `registration.json` into the new directory. Existing destinations, changed inputs, overlapping periods and invalid baselines are refused. A failure may retain a partial private model copy; keep it for inspection and do not treat a missing registration receipt as success. This is unsigned local consistency evidence, not independent artifact/source authentication.

The declared June source URL follows the project's existing BTS monthly URL pattern; availability, archive identity, source purpose/rights and row quality have not been established by this command. The current local archive inventory contains January–May only. A later data-admission step must obtain and validate the exact June archive **after the freeze**. Before candidate rows are opened, a future evaluator must implement and create an exclusive attempt receipt, retain failures, and prevent repeat evaluation. This registrar does not implement the evaluator or global single-use enforcement, and copying the same plan into another directory does not create another independent experiment.

No candidate rows or labels are read, no metrics or confidence intervals are computed, no new model is trained, and no data is imported into the active application database. The existing scenario API remains restricted to its documented January–May research window. This registration does not expand prediction serving or qualify any production requirement.

Focused checks: `python -m unittest discover -s tests -p test_evaluation_registration.py`. They use synthetic non-pickle artifact bytes and explicitly amended metadata, without inference or candidate data. A separate native registration receipt is needed to demonstrate the actual trusted model was frozen.
