# Historical research model recovery parity

`infra.research_model_recovery` checks the existing delay-v2 artifact's inference before and after backup/restore in a new synthetic schema-8 state. It never opens the original snapshot's flight database, restores real user accounts, retrains the model, evaluates airline accuracy or deploys anything.

## Operator invocation

```powershell
.\.venv\Scripts\python.exe -m infra.research_model_recovery --snapshot "<reviewed local snapshot directory>" --manifest-sha256 "<64-character manifest SHA-256>" --trusted-local-model
```

The trust flag is an explicit OS-owner decision to load the pinned executable joblib artifact. Do not use it with an untrusted downloaded model. Manifest/report hashes provide local byte consistency, not publisher authentication. The module is a CLI only, not an API accepting uploads or arbitrary model paths.

The manifest must be a bounded ordinary local file with an exact caller-supplied digest, unique allowlisted inventory entries, schema 7 or 8 metadata and a valid snapshot UUID. Only the model and model report are opened/copied from that snapshot. Symlinks/junctions, network paths, changed bytes, incomplete pairs, duplicate JSON keys and an absent research gate are refused before deserialization. The source database is deliberately not required or verified. A schema-7 snapshot's model pair can be reused without migrating its database.

## Measured flow

1. Capture the source manifest/model/report pins. Copy only the verified model pair into a fresh private case; check copy hashes.
2. Start a fresh Python subprocess with state paths bound to that case, workers/monitor off. Initialize schema 8 with one synthetic administrator, session and synthetic flight row. Original accounts and flight rows are not copied.
3. Run the unchanged `ResearchPredictor` for three fixed historical AA/JFK/LAX scenarios (January, April and May 15, 2025, at 09:00). Each result must retain research-only warnings and no operational approval.
4. Back up the synthetic state and copied model, restore into a new directory, and run a new predictor. Complete result objects must match exactly for all three scenarios. This tests recovery parity, not an independent holdout or prediction benefit.
5. Verify restored-session revocation, source-state preservation and offline row/receipt/event consistency before testing a fresh restored login. Recheck the source manifest and model/report pins after the subprocess.

The report is `.local/research-model-recovery/<case>/report.json`. It records source snapshot/manifest/artifact pins, harness revision and dirty-tree observation, verifier source hash, prediction results, restore receipt and offline evidence. Keep reports, copied model binaries, credentials, snapshots and logs out of Git. Fresh synthetic passwords exist only in worker memory. Failure reports omit worker stderr and return a generic diagnostic.

## Tests and limits

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_research_model_recovery -v
npm.cmd test
```

Tests reject missing trust, altered pins, malformed inventories, duplicate keys and absent research gates before any model execution. A fitted synthetic classifier is exercised in a real isolated worker through backup, restore, exact prediction comparison, audited revocation and login. Generic worker failure must preserve the source pair.

An operator run can use the existing locally trained historical US model; that does not authenticate its publisher, qualify UAE operations or establish new model accuracy. This increment does not recover the full historical flight database, retrieval index, Ollama weights or a browser session. It does not measure encrypted/off-host recovery, independent key custody, process confinement or production service recovery objectives. The child has a time budget but is not a security sandbox for untrusted pickle code. Production acceptance remains open.
