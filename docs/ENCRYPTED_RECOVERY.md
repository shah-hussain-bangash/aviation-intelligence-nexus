# Encrypted local recovery

AIN can seal a verified recovery snapshot into authenticated ciphertext and restore it to a new private directory. A real workstation drill recovered **2,835,101 flights**, the active v2 model and document index. Account records were preserved, restored sessions revoked, and the restored prediction matched the native result exactly. This is a separate local drill, not a replacement of the running database or qualification for recovery after computer loss.

## Encryption and key boundary

The operator tool uses the `cryptography` library's [Cobblestone-128 streaming recipe](https://cryptography.io/en/stable/cobblestone/), with a randomly generated key and fixed AIN version context. It processes bounded chunks rather than loading the full database into memory. It authenticates the complete ciphertext before parsing the compressed archive. Archive members are allowlisted, links/duplicates/traversal are rejected, and the original schema/checksum/row-count checks still run before the final restore target is created.

The local key file is protected using [Windows DPAPI CurrentUser](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata), without the machine-wide access flag. It sits outside the checkout; key bytes are never printed or passed on command lines. DPAPI normally depends on the Windows user profile and computer. This is **not independent key escrow**: losing that profile/computer can make this backup unrecoverable. No portable key-export workflow, off-site storage, key rotation or recovery on another computer is qualified.

The CLI key provider runs in the normal signed-in Windows session. Encryption primitives are tested on Linux too, but Linux cannot open the Windows DPAPI key. The dashboard containers do not receive the key or run the encryption CLI. Keep keys and encrypted archives out of Git. Authentication protects against changes without the key; it does not make an untrusted key holder or serialized model safe. Restore only your own trusted snapshots.

## Operator commands

Install the operator dependency snapshot alongside the API environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r services/api/requirements-lock.txt -r infra/requirements-lock.txt
```

From the checkout, create a key **once** in a private directory outside the checkout. The sibling directory in this example is outside the project's Git repository. Never replace an existing key to resolve an error:

```powershell
.\.venv\Scripts\python.exe -m infra.sealed_recovery keygen --key-file ../.ain-recovery-keys/aviation-local.dpapi
```

Create a new consistent snapshot using [the recovery runbook](LOCAL_DEPLOYMENT_RECOVERY.md), then seal it and restore to a new destination:

```powershell
.\.venv\Scripts\python.exe -m infra.sealed_recovery seal --key-file ../.ain-recovery-keys/aviation-local.dpapi --source .local/recovery/backups/my-new-snapshot --destination .local/recovery/sealed/my-new-snapshot.ainseal
.\.venv\Scripts\python.exe -m infra.sealed_recovery restore --key-file ../.ain-recovery-keys/aviation-local.dpapi --source .local/recovery/sealed/my-new-snapshot.ainseal --destination .local/recovery/restores/my-new-encrypted-drill
```

Existing key files, encrypted outputs and restore targets are refused. The tool does not overwrite live state. It supports local snapshots and encrypted envelopes up to eight GiB, subject to free space. Snapshot files must remain unchanged while sealing. Publication uses an exclusive hard link on the tested local filesystem; this is not qualified on arbitrary network filesystems.

The original plaintext snapshot remains in place. Older unencrypted backups are also preserved. The tool temporarily decrypts to private staging during restore, then removes its staging files on normal success/failure. This is not secure erasure, and interruption/crash cleanup is not guaranteed. Encryption does not retroactively protect original data, plaintext snapshots or an already compromised Windows session. Backup rotation and automatic deletion are deliberately not implemented.

## Evidence and dashboard

The encrypted drill produced an 86,642,676-byte archive. Restoration authenticated the ciphertext, verified database integrity and row counts, preserved account records, restored model/index artifacts and revoked restored sessions. The file-copy/restore-validation portion took 15,207.07 ms; that timing excludes decryption, provisioning and user acceptance and is not a full-system RTO. The restored historical prediction was 0.14414301173592028, matching the existing research scenario exactly.

**Know what is running** separately displays the local encrypted-drill receipt. It does not relabel the current instance's earlier unencrypted restoration. The receipt is an ordinary sanitized local file, not a protected audit, current backup schedule or proof that all backups are encrypted. See [the measured evidence](reports/Encrypted_Recovery.json).

The Windows suite now passes **128 tests: 107 Python and 21 Node**. Linux runs the same suite with the Windows-only DPAPI provider test explicitly skipped. Tests cover wrong keys, tampering, truncation/appending, unsafe archives, invalid snapshots, no-overwrite behavior, receipt qualification and secret/path exclusion. No real account password is used in tests. These checks do not constitute an independent cryptographic audit or complete production security/recovery acceptance.
