# Opt-in authenticated synthetic scoring API

25 November 2026. Local research integration; disabled in the default application and unchanged in the running deployment.

An operator can explicitly construct `SyntheticScoringService(catalog, datasets)` and pass it as the `synthetic_scoring` argument to `services.api.main.create_app`. `datasets` is a server-owned mapping of at most ten bounded dataset IDs to `(local_feature_path, recorded_sha256)` pairs. Neither the request body nor a query parameter can configure a path, catalog, artifact or dataset. There is no environment activation, automatic fixture discovery or fallback to real flight data. The default factory passes no service.

Authenticated admin/researcher accounts can use:

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v1/research/synthetic-scoring` | Return the observed revision, selected model and configured dataset IDs/hashes without paths. Default application returns `available:false`. |
| `POST /api/v1/research/synthetic-score` | Score one configured synthetic dataset under explicit revision/model/input pins and `acknowledged:true`. Default application refuses with 503. |

The POST JSON contains exactly `dataset_id`, `expected_revision`, `model_sha256`, `features_sha256`, and `acknowledged`. Types are strict; extra fields, path-like IDs, negative/unsupported revisions and false acknowledgment are refused. Query parameters are rejected. Existing API session, same-origin and CSRF controls apply, and viewers cannot inspect the context or score. The scoring route rechecks the current account/session before and after execution; an observed revocation/access change withholds predictions. No new account or password mechanism is introduced.

The service invokes the prior catalog-selected scorer, preserving its bounded synthetic schema, exact bundle/feature checks and before/after catalog observations. Responses retain dataset, catalog snapshot/revision, selection event, artifact/state/evaluation and prediction identities. Free-text selection reasons and server paths are omitted. Results are marked synthetic, not saved to history, and not production/operationally approved. Configuration, changed-evidence and execution failures return generic 503 responses without predictions or private paths. Existing response request IDs and no-store headers remain in use.

The frontend proxy allowlist and dashboard are intentionally not changed in this increment; the new API path is not yet a browser dashboard journey. The verified execution uses FastAPI's in-process test client, temporary schema-8 account databases and disposable catalogs built from the retained synthetic bundle. It does not bind a network port, rebuild containers, deploy source or access the user's account/data database.

Focused verification:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_synthetic_scoring_api.py
```

Eight cases cover successful projections and catalog preservation, anonymous denial, researcher/viewer roles, origin/CSRF/query/path rejection before execution, default-disabled factory, mid-execution logout, generic changed/stale evidence refusal and strict request/configuration validation. The complete regression suite and final-revision GitHub checks remain required for each change. Lazy research-module imports prevent the optional service from creating a cycle with the existing importer/API dependency.

This is a local prototype permission boundary, not managed identity, MFA, HTTPS, protected scoring history or independent authorization infrastructure. Catalog/pin forgery by the OS owner, non-atomic before/after observations, representative model quality, real-data approval, service load/concurrency qualification, authenticated dashboard integration and production acceptance remain open. No catalog management write endpoint, model fitting, heldout retuning, operational action or deployed model replacement is provided.
