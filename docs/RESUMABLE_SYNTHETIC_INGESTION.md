# Resumable synthetic incremental ingestion

Fifth new local data-platform increment, 24 November 2026. A durable local research queue now joins batch progress to the replay-safe importer. Its fixture writer generates synthetic BTS-schema archives, and its worker always imports with the synthetic source flag. It has no web route, cloud integration, production scheduler or public-data approval authority.

## Ownership and stored state

`pipelines.synthetic_ingestion.create_case(directory)` creates an exclusive fresh case with a synthetic marker, retained generated `archives/`, a queue database and an OS worker lock. `enqueue` accepts at most 10,000 generated rows per job and 100 jobs per case. Records are generated through the existing fixture writer; these are trusted OS-owner research functions, not a public untrusted upload parser. Row-count bounds do not independently cap arbitrary caller-created field payloads.

The case's application-shaped flight database is named `flights.sqlite3`; the queue is separate `queue.sqlite3`. No primary application database or schema migration is selected by the demonstration. The marker and fixed case filenames prevent accidental selection of ordinary application folders. They are not authentication against an OS owner who edits files or forges a case. Local unredirected paths are required; container, agent-job and monitor execution is refused. Raw records, queue databases and retained archives stay private under `.local`.

Queue rows record the generated job ID, period, expected archive hash, state, attempt count, fixed reason and latest importer result. This is durable current state, not a complete per-attempt audit history. Archives can remain orphaned if enqueue fails after writing a file; they are retained rather than deleted automatically. File creation and queue registration are not one filesystem/database transaction.

## Worker, crash and retry policy

`work_one(case)` holds a nonblocking OS lock for the entire claim/import/acknowledgment sequence. Windows uses a byte-range lock; POSIX uses `flock`. Another participating process cannot claim or enqueue in that case while the worker owns the lock. Operating-system process exit releases the lock. This is a single-host, serialized case worker, not distributed locking or protection from clients that bypass the protocol.

Under that lock, a new invocation can safely requeue an interrupted `running` job. Claim and attempt increment commit before import. A successful import commits flight rows and its archive ledger together, then the worker separately records queue success. If the process exits between those commits, the next attempt sees `already_imported` and acknowledges the existing ledger without inserting duplicate rows. These are replay-safe effects with possible repeated attempts, not exactly-once execution or an atomic transaction spanning both databases.

Each attempt supplies the queue's expected SHA-256 to the importer. The importer compares it to the captured private archive bytes **before database initialization or mutation**. A malformed expected hash or byte mismatch is refused. This optional library argument preserves existing calls and normalization; the privileged historical CLI/default database behavior is unchanged. Hash agreement is local consistency, not source authenticity or import approval.

Invalid/conflicting/missing archives are quarantined with a fixed reason. A busy/locked SQLite error (including extended error codes) returns the job to `queued`, up to three attempts. The caller decides when to invoke the worker again; there is no timed retry loop or backoff scheduler. Other operational database errors become `blocked` for review. Unexpected exceptions leave `running` for recovery on the next invocation. Repeated interruptions or exhausted busy attempts end in quarantine.

Quarantine does not undo an earlier committed import: for example, repeated crashes after data commit can exhaust attempts before acknowledgment. Review the retained ledger and archives before deciding what happened. There is no automatic deletion, correction, approval, blocked-job reset or compensation action. Queue commit failure after import also leaves recovery to a later invocation. These boundaries are deliberate reasons production orchestration remains open.

Jobs run in sequence among queued items. A blocked or quarantined job does not prevent later independent jobs from being selected; the library does not enforce inter-batch dependencies or assume adjacent months depend on each other.

## Reproduce an abrupt process exit

```powershell
.\.venv\Scripts\python.exe -m pipelines.verify_incremental_ingestion
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_incremental_ingestion.py -v
npm.cmd test
```

The command accepts no existing archive, database or case argument. It creates a fresh `.local/incremental-ingestion/<case_id>/`, queues three generated batches, and launches a separate worker process. That child deliberately calls `os._exit(73)` immediately after the first data commit, before queue acknowledgment. The main verifier observes persisted `running` state, resumes it, imports the next month, then quarantines a conflicting third batch. The conflicting batch tries a new row before the conflict, so its rollback is observable.

Eleven demonstration checks reconcile four final synthetic flight identities and two import ledgers, zero observed BTS rows, successful replay, bounded progress, quarantine and retained archive hashes. The report includes exact source revision/dirty state where available, participating source hashes and queue result metadata. The first replay result links back to its queued archive hash and retained generated source. Source identity also includes the reused fixture/identity helper's dependencies. This is not authenticated provenance for an external dataset.

Focused tests also verify exclusion by a live worker in a separate process, expected-hash refusal before database creation, bounded busy/crash attempts, blocked errors, case admission and private failure reporting. All application-shaped databases in the demonstration are synthetic research cases. Existing historical records, model experiments, user accounts and the running dashboard remain unchanged.

Source authorization and signed approvals, a real incremental source adapter, scheduled/backoff execution, dependency and retention policy, representative-volume recovery, distributed ownership, operational monitoring and final-image release qualification remain open. This increment does not close the data-platform phase or establish production readiness.
