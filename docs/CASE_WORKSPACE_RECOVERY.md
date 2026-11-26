# Local paired research-case recovery

The opt-in native case workspace stores accounts, saved results and audit records in `ain.sqlite3`, and cases in `research-cases.sqlite3`. Both must be captured together. The separate `infra.case_recovery` command creates an unsigned, **plaintext local backup** with an externally recorded manifest SHA-256. Existing `infra.recovery` and encrypted recovery formats do not automatically cover the case sidecar.

## Operator sequence

Stop the native workspace, gateway and background work through their owning terminals. Keep artifact/index writers stopped throughout capture. This command does not stop services or prove that shutdown occurred. Use an explicitly chosen research workspace; do not substitute the current release database or rebuild the Docker release. Source filenames must be `ain.sqlite3` and `research-cases.sqlite3`, with case schema 4 and primary schema 8.

From the repository root, after replacing `my-research-state` with the chosen local state directory:

```powershell
.\.venv\Scripts\python.exe -m infra.case_recovery backup --source .local/my-research-state --destination .local/case-backup-01 --offline-acknowledged
```

Retain the returned `manifest_sha256` separately. Use its exact value below in place of `RECORDED_SHA256`; do not calculate a replacement pin from an untrusted or changed bundle.

```powershell
.\.venv\Scripts\python.exe -m infra.case_recovery verify --source .local/case-backup-01 --manifest-sha256 RECORDED_SHA256
.\.venv\Scripts\python.exe -m infra.case_recovery restore --source .local/case-backup-01 --destination .local/case-restored-01 --manifest-sha256 RECORDED_SHA256 --offline-acknowledged
```

Writes require a new directory under `.local`; library calls also reject existing destinations, overlap, redirected paths and network sources. No existing workspace is replaced. Successful restoration revokes only restored sessions and adds the existing primary sign-out audit record. Original account passwords remain unchanged. Review the receipt before explicitly configuring the native factory for the new directory using [the case workspace instructions](RESEARCH_CASE_WORKFLOW.md). There is no automatic startup, release selection, merge or deployment.

## What is checked

- Two SQLite `BEGIN IMMEDIATE` guards exclude database writers while separate read connections capture committed state. Active queued/running agent work is refused. SQLite copies are converted to standalone DELETE-journal files before receipt hashes are sealed; source journal mode is not changed.
- Primary migration/audit contracts, database integrity, exact case table inventory, event continuity, source/attachment hashes, closing outcome, owner IDs and all retained evidence/agent/gate snapshots are checked. Case validation uses projections without initializing or migrating the source store. Owners must still exist, even if inactive; current role permissions are rechecked by normal authentication after restoration.
- The primary inventory includes saved records and any existing active delay-v2 model/report and knowledge-index files. Raw aviation archives, other models, Ollama weights and arbitrary state files are excluded. Optional artifacts are copied and checked; model bytes are never deserialized by recovery. This is not model/index usability qualification.
- A partial backup/restore retains its `restore-in-progress.json` marker. The native factory refuses it before constructing a case store. Completed backup bundles also cannot be started directly as workspaces. Restore uses a child staging directory and keeps it for inspection, so it retains another plaintext copy of primary state.
- Pinned manifest, file inventory, sizes and SHA-256 values are checked before restoration. The full case content fingerprint must agree afterward. A changed pin, altered file, extra file, missing owner, incompatible schema or interrupted copy fails closed.

Focused verification: `python -m unittest tests.test_case_recovery -v`. The synthetic fixture contains one closed case with six events: opened, note, evidence, reviewed-agent snapshot, reviewed synthetic gate proposal and closing outcome. Reviews are synthetic fixtures, not human acceptance. Restored owner authentication and all three retained-read routes are exercised; a different viewer cannot access them. The CLI is exercised for backup, verification, new-directory restoration and existing-target rejection. Optional model/index tests use inert bytes, not a serving model.

## Limits still open

This is local recovery evidence, not production qualification. Hashes and owner bindings provide consistency, not independent source authentication or tamper-proof audit. The filesystem owner can alter both data and an unprotected pin. External artifact writers rely on the operator's offline acknowledgement; the database guards do not lock external files. Directory-marker ordering is not a tested power-loss durability guarantee. Do not clear an incomplete marker to bypass failed checks.

Encryption of this paired format, off-host storage and independent key recovery, retention/deletion policy, host-loss recovery, representative load, original-user acceptance and final deployed-release recovery remain unimplemented or unqualified. No automated cleanup removes incomplete targets, staging copies, source records or backups. Keep all of them private and out of Git. All 24 production acceptance requirements remain open.
