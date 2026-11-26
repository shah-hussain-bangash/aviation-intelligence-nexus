# Offline index repair after an interrupted rehearsal

An abrupt process exit can bypass the `finally` block of the [isolated index recovery rehearsal](RETRIEVAL_INDEX_RECOVERY.md), leaving its original bytes in `retained-knowledge-index.json`. `infra.recover_retrieval_index` provides an explicit, guarded **offline artifact repair** for that private case. It does not install automatic recovery or select a live deployment.

## Operator procedure

First stop all test services belonging to the interrupted case and confirm no runner is still using it. This tool does not find or stop orphaned processes. `--offline` is your declaration that this has been done; it is not independent proof of process shutdown. Do not use the command against a running case.

Obtain the SHA-256 of that case's existing `plan.json`, verify that it is the intended plan, then run:

```powershell
.\.venv\Scripts\python.exe -m infra.recover_retrieval_index --case .local/restored-api/<32-hex-case> --plan-sha256 <full-lowercase-plan-sha256> --offline
```

The command requires an ordinary local case directly below `.local/restored-api`, the exact plan bytes, explicit retrieval/recovery mode with prediction disabled, and the plan's recorded index hash. The original retained file must match that hash and pass envelope/vector/model-identity checks and exact current six-document corpus binding. Symlinks/junctions, other cases, changed plans/files and an existing index destination are refused.

The tool creates only the missing `state/knowledge/index.json`, using exclusive creation and an independent bounded byte copy. It keeps the retained original and never overwrites a destination appearing concurrently. Hashes of the restored file, retained source and plan are checked afterward. Repeating the command with an existing destination is refused. Later rebuilding the restored index cannot modify the retained copy through a shared hardlink.

A fresh receipt is written under `.local/index-repairs/<unique-case>/report.json`, recording source/plan/index hashes, code revision and scope. If a write/post-copy check fails, the receipt remains failed and the destination may need inspection. Do not start services using an unverified or partial file. Interrupted repair itself is not an atomic directory publication: the original retained bytes remain available, and no partial output is automatically deleted.

## Evidence and limits

The separate [repaired-index service/search rehearsal](REPAIRED_INDEX_SEARCH.md) starts normal local services on another index copy with fresh synthetic accounts and an empty database. It does not start the original repaired case or qualify its database/account recovery.

Focused check: `python -m unittest tests.test_recover_retrieval_index -v`. Fixtures cover actual abrupt worker exit, offline declaration and plan pins, forged corpus/model identity, changed retained bytes, nonowned cases, independent-copy preservation and a destination race. The tests assert that repair contacts neither SQLite nor Ollama. Run `npm test` for regression checks.

Native verification should create a fresh synthetic rehearsal case, copy only the existing project index into it, terminate its own fault worker without cleanup, and run the versioned repair CLI. This avoids another flight-database copy and never interrupts shared services. Synthetic fixture metadata is not an original interrupted user's case or a protected recovery attestation.

Hashes and `--offline` are unsigned operator evidence, not authentication or service-liveness proof. This command does not repair databases, restore model weights, contact a provider, execute search, restart services, authenticate a real user or establish generated-answer quality, off-host recovery or production readiness. Follow with separate qualified service/search checks before considering use of a repaired real case. All production acceptance requirements remain open.
