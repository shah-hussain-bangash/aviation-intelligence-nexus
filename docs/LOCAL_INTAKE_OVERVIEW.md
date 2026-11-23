# Local intake overview

The administrator dashboard can display a read-only historical snapshot of retained BTS preflight runs. This is separate from the imported-flight database and its quality audit. No upload, import, model training or source authorization is performed by this feature.

From the repository folder, export metadata with:

```powershell
.\.venv\Scripts\python.exe -m pipelines.intake_overview
```

The exporter checks receipts and archive SHA-256 values beneath `.local/intake/accepted` and `.local/intake/quarantined`. It does not rescan CSV rows. It considers at most 1,000 run entries and 100 distinct accepted archives with a cooperative 120-second budget. Missing or inconsistent run artifacts count as unverifiable. Contradictory period, size or row claims for the same accepted SHA-256 prevent publication of the entire new snapshot. Identical accepted hashes count once toward declared row totals. Quarantine counts refer to runs, not unique archives.

The output `.local/intake-dashboard/snapshot.json` contains only bounded metadata. Replacing it is atomic; earlier snapshots are retained as uniquely named `previous-*.json` files. Collection failures leave the previous snapshot in place, whose recorded timestamp remains visible. Checksum validation detects accidental changes; someone able to edit both payload and checksum can forge a consistent snapshot. It is unsigned local evidence, not an audit trail or current inventory. An empty retained directory can produce an empty snapshot.

For native execution the API reads `intake-dashboard/snapshot.json` beside the selected database. For Docker, add `infra/compose.intake.yaml` after the base compose file and retain the observer overlay if already installed. This mounts **only** `.local/intake-dashboard` at `/intake-status`, read-only, with automatic host-directory creation disabled. The API requires `AIN_INTAKE_OVERVIEW_MOUNTED=1` to use that fixed path. Raw archives stay outside the mount. Do not put raw data or credentials in the metadata directory.

`GET /api/v1/research/intake-overview` requires an authenticated administrator. Anonymous requests receive 401, other roles 403, and query controls 422. Invalid or absent metadata returns 503 with a fixed error. The dashboard hides the card from other roles, clears results on session changes and refresh failures, and supports a local JSON export of the displayed snapshot. Refresh fetches the saved snapshot; it does not run the host exporter.

Synthetic browser fixtures checked desktop and an actual 433px narrow viewport, viewer hiding, sign-out clearing and failed-refresh clearing. Python tests cover actual deduplication, quarantine/unverifiable accounting, contradictory unsigned claims, preservation, metadata limits, fixed mount selection and API authorization. Node tests cover rendering, count consistency and proxy rejection. These checks do not qualify the application for airline operations or close any of the 24 production requirements.
