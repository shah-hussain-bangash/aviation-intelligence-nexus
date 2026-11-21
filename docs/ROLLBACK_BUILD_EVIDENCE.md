# Rollback evidence for the running build

The Release & recovery panel compares a version-2 isolated application rollback receipt with the running source revision, verified database schema and a digest of ten selected persisted-state source contracts. All three must match before the panel says that the recorded drill covers this candidate. This is a bounded local compatibility check, not complete application compatibility or production acceptance.

Historical version-1 receipts remain visible, explicitly unbound. Different releases, changed schemas/contracts, unavailable source fingerprints and unverified development builds cannot receive a current-build match. Refresh failures clear the previous display and disable export. Sign-out or account replacement cancels pending requests and clears export state. Signed-in viewers can read this deployment information; the panel exposes no rollback operation.

The JSON export allowlists display metadata, binding and limitations. It contains no account fingerprints, credentials, private paths or raw restore contents. Local receipts are editable operator records, not cryptographic attestations or protected audit logs.

## Operator procedure

Retain the current immutable API/web image pair with `python -m infra.releases capture --output .local/releases/baseline.json`, and give both retained images separate local tags before building another release. Confirm the approved project, idle job queue, source revisions, state contracts and schema. Use fresh filenames; evidence capture refuses overwriting existing files.

The drill controller mutates only `ain-rollback-drill`, loopback port 8091 and that project's own named state volume. It refuses a primary-volume mount, schema downgrade, changed selected contracts, active investigations, mutable image tags or uncommitted source identities. Before reusing a retained restored volume, check its schema, inactive queue and model/index read-only. Reusing an earlier restored copy does not constitute a fresh backup or restore.

Capture the deployed candidate, prepare its isolated override, start the candidate on the separately restored drill volume, then run:

```powershell
python -m infra.releases capture --output .local/releases/candidate.json
python -m infra.releases prepare --current .local/releases/candidate.json --output .local/releases/prepared.json
# Start only the isolated candidate using the generated override, disabled worker and port 8091.
python -m infra.releases drill --current .local/releases/candidate.json --target .local/releases/baseline.json --output .local/releases/completed-drill.json
python -m infra.publish_rollback --receipt .local/releases/completed-drill.json
```

Before starting containers, inspect the override and explicit Compose project/port. Existing runbook [Local release rollback](LOCAL_RELEASE_ROLLBACK.md) describes the isolated Compose startup. Never mount the primary state volume into the drill. The controller checks deployment health before and after switching, selected table counts, internal account fingerprint, model/index bytes and a fixed historical research prediction. It attempts to return the isolated candidate even if target verification fails. A failed drill produces no success receipt.

The operator publisher checks the exact currently deployed API/web image pair, revision, schema and selected contracts against the completed receipt. The running API rechecks its own source/schema/contracts before atomically installing the sanitized display record. A previous receipt is preserved under a unique history filename; identical publication is idempotent. This action writes only local evidence metadata and does not switch releases, change accounts or migrate the database.

Store the measured runtime receipt outside Git. Adding it as another source commit would create a different candidate revision from the one tested. A source archive and CI should cover the actual candidate commit; a later revision requires a new drill for a matching receipt.

## Verification and limits

Python tests exercise current/other revisions, schema/contract changes, missing contracts, legacy records, malformed receipts, exact-image publication rejection, metadata sanitization, preserved history and idempotence. Browser fixture checks cover desktop/mobile layouts, historical/incompatible receipts, export, viewer access, refresh failures and session replacement. [Browser checks](reports/Rollback_Binding_Browser.json) use synthetic receipts and establish UI behavior only; they do not represent a measured application rollback.

The actual completed rollback result is generated at runtime, then shown in the authenticated dashboard. No success is inferred merely from code or a past drill. Same-machine image retention, selected-state parity and local health checks do not qualify database downgrade, model/prompt rollback, zero downtime, off-site recovery, high availability or production failover. All 24 production requirements remain open.
