# Trace one January research batch

The recorded January data-quality result now links to `#batch-lineage`. A separate read-only card joins its pinned import manifest to one retained intake record using the **complete archive SHA-256**, with matching period and receipt row count. The card shows the declared public BTS URL, accepted run identifier, exact receipt-byte SHA-256 and pinned audit-report SHA-256.

This establishes an archive identity recheck performed after import. It does not claim that the new preflight receipt caused the original import, authenticate the source, check current database contents or import records. Historical US flight evidence is separate from the platform's synthetic operational scenarios. No production acceptance is implied.

## Access paths

- Administrator: existing sign-in, Data quality and lineage, January trace link, then “Administrator · Inspect full intake receipt”. `GET /api/v1/research/batch-lineage` includes the validated full receipt only for this role.
- Analyst (`researcher`) and read-only `viewer`: the same link and endpoint return the recorded dataset, source and exact receipt reference; the full receipt is excluded server-side. The existing admin-only intake overview remains forbidden to these roles.
- Anonymous: 401. Query selectors: 422 after authentication. There is no write route, upload, arbitrary path or archive selector. Missing/invalid metadata: 503. Session changes and failed refreshes clear displayed evidence.

## Reproduce in a separate local research folder

Use a new ignored `.local` research folder, preserving earlier runs:

```powershell
.\.venv\Scripts\python.exe -m pipelines.intake_bts .local/downloads/bts_2025_01.zip --year 2025 --month 1 --directory .local/example-lineage/intake
.\.venv\Scripts\python.exe -m pipelines.verify_intake .local/example-lineage/intake/accepted/<run-id>
.\.venv\Scripts\python.exe -m pipelines.batch_lineage .local/example-lineage/intake/accepted/<run-id> --state .local/example-lineage/state
```

The exporter verifies archive bytes, preserves the original receipt text and writes metadata to `state/intake-dashboard/batch-lineage.json`. Receipt reads are bounded to 64,000 bytes and checked for file identity/size/time changes; the exact bytes must also match before and after archive verification. These checks detect observed concurrent changes but do not authenticate an editable local owner. Existing lineage files are never replaced. Raw archives stay in private intake storage. The native API reads this fixed metadata name beside its selected research database. A future separately approved container release can use the existing read-only `/intake-status` metadata mount; this change does not deploy or modify the existing mounted snapshot.

The metadata is unsigned and editable by the local owner. The API rechecks receipt structure, exact receipt-byte digest and the pinned audit-manifest join; it does not reread raw archives on HTTP requests. A consistent forgery of receipt and metadata is outside this assurance boundary. Only January's pinned recorded batch is supported; other months fail closed.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_batch_lineage tests.test_intake_bts tests.test_verify_intake tests.test_intake_overview -q
npm.cmd run test:web
npm.cmd run check
```

The implementation also passed the full established `npm.cmd test` suite locally. Browser evidence uses actual isolated API projections from the retained public January archive and explicitly synthetic role controls. Disposable accounts and the verification database are separate from the user's account and primary deployment. The local evidence report records the exact source baseline, source hashes, run and receipt identifiers, API role outcomes and screenshots. No raw dataset, private database or full receipt is committed with this documentation.
