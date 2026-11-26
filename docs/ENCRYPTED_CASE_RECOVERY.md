# Encrypted paired research-case backups

`infra.sealed_case_recovery` encrypts an already verified [paired case backup](CASE_WORKSPACE_RECOVERY.md). Its separate `ain-sealed-case-v1` format uses AES-128-GCM, a fresh random 12-byte nonce and full 16-byte authentication tag. The format header and nonce are authenticated with the ciphertext. It follows the library's [GCM authentication guidance](https://cryptography.io/en/stable/hazmat/primitives/symmetric-encryption/): no archive parsing or destination creation occurs until tag verification succeeds. This format does not change existing encrypted backups or the running dashboard.

## Explicit local operator steps

First stop the chosen research workspace and artifact writers and make a paired backup using the earlier instructions. Retain its returned manifest SHA-256 separately. Do not recalculate a replacement pin from an untrusted bundle. Use a dedicated Windows CurrentUser DPAPI key outside the checkout, through the existing protected-key generator. Never paste key bytes into a command, chat, environment variable or repository file.

```powershell
$caseRecoveryKey = Join-Path $env:LOCALAPPDATA 'AIN/case-recovery-aes.dpapi'
.\.venv\Scripts\python.exe -m infra.sealed_recovery keygen --key-file $caseRecoveryKey
```

The generator refuses an existing key file. Keep this dedicated key separate from keys used for other backup formats. Do not overwrite or remove a key needed by earlier backups. Key creation does not provide independent/off-host key escrow or key rotation. DPAPI ties this file to the Windows user and its protection environment; copying the protected file alone is not host-loss recovery.

Replace `RECORDED_SHA256` below with the original paired manifest pin. Destinations must be new paths under `.local`. The source is the completed backup directory, not live state.

```powershell
.\.venv\Scripts\python.exe -m infra.sealed_case_recovery seal --source .local/case-backup-01 --destination .local/sealed-cases-01.aincase --key-file $caseRecoveryKey --manifest-sha256 RECORDED_SHA256 --offline-acknowledged
.\.venv\Scripts\python.exe -m infra.sealed_case_recovery restore --source .local/sealed-cases-01.aincase --destination .local/case-restored-02 --key-file $caseRecoveryKey --manifest-sha256 RECORDED_SHA256 --offline-acknowledged
```

Record the ciphertext SHA-256 and snapshot identity from sealing, along with the separately retained manifest pin. Successful restoration authenticates the encrypted source, verifies the original manifest and exact inventory, and invokes paired recovery into a fresh directory. It preserves case contents and revokes restored sessions. The additional `case-encrypted-restore.json` receipt binds the source ciphertext, original manifest pin, snapshot identity and restored case fingerprint. It does not change account passwords or start services.

## Boundaries and failure behavior

- Key bytes are loaded through the existing Windows provider, not accepted as command-line arguments. Cross-platform tests use ephemeral synthetic keys; the actual CLI/key-provider roundtrip is separately tested on Windows. No existing user key is changed by those tests.
- Streaming encryption avoids loading the whole snapshot into memory. Eight GiB limits apply independently to ciphertext and expanded archive contents. The archive accepts only the fixed paired-backup filenames, regular files, no duplicate names, links, traversal or unknown entries. Both manifests are limited to 64,000 bytes. Optional model/index bytes remain subject to existing paired verification, without model deserialization.
- Wrong keys, changed headers/nonces/tags, modified/truncated/appended ciphertext, unsafe archives and changed manifest pins fail before a restore target is created. Authentication alone does not certify the backup's purpose, source rights, reviewer identity or semantic correctness.
- Publication uses an exclusive hard link from a freshly created partial file, preserving existing outputs. Interrupted publication removes only its own partial file. This requires local filesystem hard-link support; unsupported publication fails rather than falling back to overwrite.
- Decryption uses private scratch files, with archive parsing only after successful authentication. Owned scratch is removed on normal exception/success paths; a process crash may leave scratch behind. There is no secure-erasure guarantee. Sources, the original plaintext paired bundle and plaintext restored/staging copies are retained. Encrypting the transport does **not** encrypt the restored workspace or remove earlier plaintext copies.
- The paired restore interlock remains in force. If writing the additional encrypted receipt fails, the code attempts to reinstate the incomplete marker and refuses factory startup. This is not a tested disk-loss or power-loss durability guarantee. Do not manually clear a failed marker to bypass checks.

Focused checks: `python -m unittest tests.test_sealed_case_recovery tests.test_case_recovery -v`. The fixture is synthetic: one closed six-event case with retained evidence, an agent report with a fixture review, and a computed synthetic gate proposal with a fixture review. Recovery preserves captured records; it does not run a new model/agent or perform an airport action. Platform skips are reported explicitly.

## Still incomplete

Off-host storage, independent key recovery, key lifecycle/usage policy, retention/deletion, secure scratch handling after host/process failure, representative data/load and final deployed-release qualification remain open. Both the source and restored workspace contain plaintext. Local authenticated encryption is not a production-ready or disaster-recovery acceptance claim. All 24 production acceptance requirements remain open.
