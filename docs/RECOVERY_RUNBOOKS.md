# Versioned synthetic recovery runbooks

These commands replace workstation-specific `.local/*.py` launchers for new rehearsals. They do not build images, access the primary deployment, merge branches or qualify a production release. Use Docker Desktop's Linux engine, the project Python environment and this checkout as the current directory. All test accounts and flight rows are synthetic.

## Pin the reviewed images

The API and web images must have full immutable `sha256:` IDs, matching full source revision labels, schema 8 and selected persisted-state contracts matching the current checkout. Mutable tags, short revisions and incompatible contracts are refused. Obtain IDs from already built, reviewed images with `docker image inspect`. No runbook silently builds or pulls an image.

Replace the following placeholders with your reviewed values:

```powershell
$apiImage = "sha256:<64 lowercase hex characters>"
$webImage = "sha256:<64 lowercase hex characters>"
$imageRevision = "<40 lowercase hex characters>"
```

Reports record harness checkout identity, dirty-tree observation and harness hashes separately from the selected images' revision. Comparing selected state-contract files is not complete application compatibility proof.

## Packaged recovery

```powershell
.\.venv\Scripts\python.exe -m infra.packaged_recovery_rehearsal --api-image $apiImage --web-image $webImage --expected-revision $imageRevision
```

This streams the versioned `infra/fixtures/packaged_recovery_probe.py` test harness into the pinned API image, exercising its packaged migration, account and recovery functions. A network-disabled, non-root container uses a read-only root and bounded temporary filesystems. Checks cover synthetic schema-7 to schema-8 upgrade, retained rows, audited restored-session revocation, restored credentials and nonexecutable placeholder artifact hashes. The streamed probe is harness code, not proof that it was packaged in the image. No real model inference occurs.

## HTTP and failure scenarios

```powershell
.\.venv\Scripts\python.exe -m infra.http_rehearsal --api-image $apiImage --web-image $webImage --expected-revision $imageRevision --scenario http
.\.venv\Scripts\python.exe -m infra.http_rehearsal --api-image $apiImage --web-image $webImage --expected-revision $imageRevision --scenario outage
.\.venv\Scripts\python.exe -m infra.http_rehearsal --api-image $apiImage --web-image $webImage --expected-revision $imageRevision --scenario automatic_restart
.\.venv\Scripts\python.exe -m infra.http_rehearsal --api-image $apiImage --web-image $webImage --expected-revision $imageRevision --scenario restore
```

Run sequentially. Default port is loopback `18090`; `--port` accepts an unused unprivileged port. Each invocation creates a new `ain-http-check-<random>` project, private default network and named state volume. Before creating resources, admission checks the resolved configuration for isolated mounts/networking, pinned images, disabled workers/monitor, read-only roots, dropped capabilities and restricted host binding. Two disposable accounts use a random password passed over stdin, never printed or stored in the report.

- `http`: container safeguards/readiness, dashboard/security headers, proxy login/read/logout, viewer mutation denial, origin and CSRF rejection.
- `outage`: explicit isolated API stop, failed readiness/proxy responses, available static dashboard, explicit restart and selected synthetic logical-state comparison.
- `automatic_restart`: temporary `on-failure:3` policy on the admitted API only; one verified Uvicorn-child crash; nonzero exit event and one Docker restart; original policy restored. This does not test health-only hangs, host reboot or redundant-node failover.
- `restore`: adds a clearly synthetic flight row and research account, logs in, stops the isolated services, snapshots state and restores to a new volume. The same isolated project then serves restored state. Old sessions must fail; the restored password/role and logout must work. Synthetic flight rows stay excluded from the real BTS summary.

Reports are private under `.local/rehearsal-reports` and each case directory. Services stop in cleanup; synthetic stopped containers/volumes remain for review. Cleanup failures make a run fail. Never use a global Docker prune to remove evidence; review the exact project/volume recorded in the report.

## Encrypted continuation on Windows

Use the successful `restore` scenario's report and an **existing** DPAPI CurrentUser key outside this checkout. Replace both path placeholders:

```powershell
.\.venv\Scripts\python.exe -m infra.encrypted_recovery_rehearsal --restore-report "<private restore report path>" --key-file "<existing Windows-protected key path>" --expected-revision $imageRevision
```

This does not generate, replace or export a key. It copies only the retained synthetic snapshot through a network-disabled, read-only helper, verifies snapshot/manifest bindings, then invokes the existing authenticated encryption and restore code. Wrong-key, modified, truncated and appended ciphertext must leave no restore target. Offline row/receipt/event consistency and original-file preservation are checked. The helper is removed; plaintext source copies remain private and retained.

Reports are unsigned operator evidence. Ciphertext authentication does not independently authenticate backup origin, historical audit or a reviewer. Same-user DPAPI recovery does not establish off-host recovery or independent key custody.

## Verification and limits

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_rehearsal_admission tests.test_sealed_recovery -v
npm.cmd test
```

Admission tests exercise unsafe projects/volumes, ports, mounts, networks, image references, workers and weakened controls without contacting Docker. Guards remain active with Python optimization enabled.

Earlier private-launcher observations on image revision `a8b8a3bc507418496f8e9cbdf6033893ef28e4f9` passed all six local scenarios. **Those results do not qualify these refactored runners.** Execute the versioned commands and retain their own reports. Real model/retrieval artifact recovery, off-host monitoring/alerts, independent recovery/key custody, HTTPS/managed identity, representative load and production acceptance remain open.
