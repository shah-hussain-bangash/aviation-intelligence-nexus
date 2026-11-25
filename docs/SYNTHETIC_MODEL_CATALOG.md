# Local synthetic model catalog

25 November 2026. Private single-host research state only. Catalog selection is metadata; it does not deploy a model or change the running dashboard.

```powershell
.\.venv\Scripts\python.exe -m ml.synthetic_model_catalog <new-private-catalog> init
.\.venv\Scripts\python.exe -m ml.synthetic_model_catalog <catalog> register <bundle.json> --bundle-sha256 <recorded-sha256>
.\.venv\Scripts\python.exe -m ml.synthetic_model_catalog <catalog> status
.\.venv\Scripts\python.exe -m ml.synthetic_model_catalog <catalog> select <registered-sha256> --expected-revision <observed-revision> --reason "Synthetic research selection"
.\.venv\Scripts\python.exe -m ml.synthetic_model_catalog <catalog> rollback <previous-sha256> --expected-revision <observed-revision> --reason "Return to previous synthetic artifact"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_synthetic_model_catalog.py
```

Initialization requires a new directory. All later operations require the existing supported catalog; there is no automatic migration or repair. The catalog uses its own SQLite database and private `bundles` directory, separate from application state. Registration requires exact raw-byte identity and the supported synthetic bundle schema, copies verified bytes under their SHA-256 filename without overwriting, and records state/receipt identities. Repeat registration of the same bytes is idempotent. File identity is the version identity: different encodings can describe the same model state and must not be presented as model-quality improvements.

Selection and rollback validate all registered artifacts and replay contiguous local history inside a database transaction. Changes require the observed revision, so competing updates from the same revision cannot both commit. Rollback accepts only the recorded previous version. Every successful registration, selection and rollback increments the revision and records the action, prior/current identity, reason and UTC time. Status opens the database read-only and verifies artifact/history consistency. An unreadable/changed bundle, history gap, inconsistent selected version, stale revision or unregistered target causes refusal. Commands print JSON and return 2 on refusal.

Limits are 100 registered files, 10,000 events and the existing 8 MiB per-bundle JSON cap. All registered bundles are checked, including inactive ones; a changed inactive file blocks changes until a human investigates. Database changes are transactional, but file creation and database commit are not one atomic operation. A failed registration may leave an unreferenced file. A later explicit registration can reuse it only if its bytes match the expected identity; corrupt partial files are refused, never silently replaced. There is no deletion/retention command, power-loss/fsync qualification or automated cleanup.

Tests cover revision races, version-selection/rollback history, idempotent registration and read-only status, changed bytes, history removal, stale/unknown requests, injected metadata failure with verified-orphan retry, no-overwrite initialization and actual CLI actions. The retained demonstration uses two serializations of the same synthetic model to exercise version identity; it neither fits a challenger nor establishes behavioral/quality rollback.

This catalog has no user authentication, role boundary, protected audit, signatures or independent registry authority. An operating-system owner can forge its database, files and supplied hashes. Registration is consistency checking, not promotion approval. No scoring API consumes the selected pointer yet, and no application/database schema, frozen experiment, real model, dashboard or deployment changes. Authorized data, independent quality review, protected model lifecycle and production acceptance remain open.
