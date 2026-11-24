# Historical intake coverage audit

This host CLI checks whether retained, verifiable intake archives cover every archive in the pinned January–May 2025 data-quality report. It extends the single-batch trace without changing dashboard routes, roles, accounts, model artifacts or deployment.

```powershell
.\.venv\Scripts\python.exe -m pipelines.lineage_coverage
```

An optional directory argument selects a different existing intake root. The default is `.local/intake`. The command prints JSON and does not create or replace reports, intake files or databases. Redirect output to a new private file when a retained report is wanted. Raw archives and per-run receipts stay outside Git.

Matching requires the full archive SHA-256, declared month and declared receipt row count to agree with the pinned recorded manifest. Equal row counts alone never establish a match. Repeated accepted checks of one archive are counted once toward coverage and row totals. Unknown accepted hashes are listed separately; quarantined and unverifiable runs never fill missing coverage. An empty-manifest month cannot be complete. Duplicate expected archive identities or contradictory accepted receipt claims fail the audit rather than inflate counts.

`coverage_complete` describes only the recorded manifest set. `needs_review` also includes unknown accepted archives, quarantine and unverifiable artifacts, so coverage can be complete while unrelated findings still require review. A missing archive is `missing`; a known hash with a different period or count claim is `claim_mismatch`.

Exit codes: **0** means complete recorded coverage without review findings; **1** means a valid report contains review findings; **2** means the audit could not be produced. Unavailability prints a fixed error without exception details or personal paths. Collection reuses the existing bounds: at most 1,000 retained run entries and 100 distinct accepted archives, with a cooperative 120-second budget.

The report records the pinned audit digest, source revision when available, working-tree-change indicator and source-text fingerprints. Source changes during development must not be represented as an unchanged committed run. Archive bytes are rehashed; CSV rows are not rescanned. Receipt counts remain unsigned editable claims. The check does not establish original-import causality, source rights/authentication, current database coverage, operational suitability or production readiness.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_lineage_coverage -q
```

Development uses synthetic temporary ZIP/receipt fixtures for negative and duplicate cases. Real local evidence uses the retained historical public BTS archive set. The feature is isolated on a separate review branch; it does not merge or deploy the single-batch PR.
