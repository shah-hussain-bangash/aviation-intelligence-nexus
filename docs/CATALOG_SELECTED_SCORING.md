# Catalog-selected synthetic scoring

25 November 2026. Read-only local research command; no scoring API or deployment.

```powershell
.\.venv\Scripts\python.exe -m ml.synthetic_model_catalog <catalog> status
.\.venv\Scripts\python.exe -m ml.score_catalog_selection <catalog> <synthetic-features.json> --expected-revision <observed-revision> --model-sha256 <selected-bundle-sha256> --features-sha256 <recorded-feature-file-sha256>
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_score_catalog_selection.py
```

Use the model identity/revision from the verified catalog status and the feature hash from the retained input record. The command refuses unspecified pins, a stale revision or a different selected model before opening feature data. It validates the catalog, reads exact pinned feature bytes and calls the existing bounded synthetic bundle scorer with the selected registered artifact. No fitting, holdout evaluation, target files, catalog changes or output-file writes are involved.

After scoring, it rechecks the feature bytes and verifies the complete catalog observation is unchanged. The result links predictions to the input SHA-256, catalog revision/snapshot fingerprint, responsible selection or rollback event, bundle/state identities and original evaluation receipt. It includes the existing prediction/baseline outputs plus a fingerprint of their complete records. Generic CLI refusals return code 2 and contain no predictions; successful JSON output returns 0. Retain output separately under a private evidence path if needed.

This completes a local register/select/score/switch/rollback/score journey. The selected pointer is consumed by this CLI only. Revision checks detect an observed switch away and back; they do not lock the catalog across the entire scoring operation or guarantee the pointer is unchanged after the last observation. An OS owner can forge files, catalog history and supplied pins; these are consistency checks, not authenticated execution or protected promotion. There is no scoring-run ledger, HTTP service, role boundary, signature, automatic model switching or deployed recovery guarantee.

Eight focused tests verify exact frozen prediction parity, unchanged files, lineage fields, stale/nonselected refusal before feature access, wrong input pins, selection/rollback-bound results, interleaved switch-away/back, input/artifact changes and CLI output/refusal behavior. The retained demonstration uses two serializations of the same synthetic bundle. Identical predictions there establish identity/routing consistency, not performance differences or real-airline validation. The original consumed synthetic holdout remains consumed; no retuning or new independent quality evaluation is performed.

The original real delay model, historical data, frozen earlier experiments, application state contracts, 64 dashboard workspaces and running deployment remain unchanged. Authenticated product integration, representative real data, model lifecycle ownership and production acceptance remain open.
