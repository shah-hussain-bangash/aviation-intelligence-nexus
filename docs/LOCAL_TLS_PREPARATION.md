# Local HTTPS material preparation

This is the first local HTTPS preparation component. It creates and validates a short-lived, self-signed certificate bundle. It does **not** enable HTTPS on the dashboard, change authentication, install a certificate in an operating-system/browser trust store, open a port or configure a public endpoint. Existing external-TLS configuration remains rejected. Gateway integration, secure-cookie/origin behavior and authenticated HTTPS journeys remain separate work.

From the project folder, choose a new private directory:

```powershell
.\.venv\Scripts\python.exe -m infra.local_tls create --output .local/tls/NEW_LOCAL_BUNDLE
```

The command creates `certificate.pem`, `private-key.pem` and `manifest.json`. It refuses existing output folders, parent traversal and output outside `.local`. The certificate expires seven days after creation, names only `localhost` and `127.0.0.1`, uses an RSA 2048-bit key and SHA-256 signature, and is a server certificate rather than a certificate authority. Keep the returned certificate SHA-256 fingerprint privately for the next check. This fingerprint identifies the DER certificate, rather than the PEM text file's bytes.

```powershell
.\.venv\Scripts\python.exe -m infra.local_tls check --directory .local/tls/NEW_LOCAL_BUNDLE --certificate-sha256 EXACT_LOWERCASE_CERTIFICATE_SHA256
```

The check requires that exact external fingerprint. It verifies the self-signature, current validity and bounded lifetime, exact loopback names, server/non-CA usage, private-key match and manifest consistency. Files must be bounded ordinary files with no redirected path components. Extra PEM material is rejected. Invalid CLI input returns a fixed error without echoing paths, key bytes or supplied values. An unsigned manifest plus a matching fingerprint establishes local consistency, not independent provenance or public trust.

The private key is **unencrypted** for later unattended local TLS loading. New file modes request owner-only access where supported; Windows protection depends on directory ACLs and is not qualified by these checks. Keep the bundle under the private project `.local` directory, outside Git and public reports. No password, existing account, original model or database is changed. `trust_installed: false` and `service_started: false` describe actions this command did not perform; they are not an audit of the machine's trust stores or other running services. There is no renewal service; create a new bundle and review its new fingerprint after expiry.

Focused verification:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_local_tls tests.test_configuration -v
npm.cmd run check
```

The TLS test starts and stops only its own ephemeral loopback fixture. It checks verified HTTPS for both loopback names, rejection without explicit client trust, hostname mismatch, output boundaries, altered pins/keys/manifests, expiry and CLI error redaction. Test certificates and keys stay in disposable private folders. A passing fixture is not an authenticated dashboard journey, managed certificate, cloud deployment or production acceptance.
