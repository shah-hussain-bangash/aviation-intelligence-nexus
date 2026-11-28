# Isolated authenticated HTTPS rehearsal

This connects the normal Node dashboard gateway and Python API through an explicitly enabled native test mode. It uses a fresh private database, separate test cookies, temporary synthetic accounts and a newly generated pinned localhost certificate. It does not convert the running dashboard, install operating-system/browser trust, create cloud resources or qualify a public service.

From the project folder:

```powershell
.\.venv\Scripts\python.exe -m infra.local_https_rehearsal --output .local/NEW_HTTPS_RUN
```

Default loopback ports are 18176 (HTTPS gateway) and 18177 (API); `--web-port` and `--api-port` accept two distinct free unprivileged ports. Existing output, redirected paths and occupied ports are refused before creating state. The runner generates private TLS files, seeds disposable admin/viewer accounts, starts its own gateway/API processes, performs authenticated requests and stops only those processes. Random passwords, session cookies and CSRF values are not saved in the result. Logs, private test state and `evaluation.json` remain under the new directory. This is a transport/API exercise, not a browser journey with the original user's account.

Clients explicitly trust the generated certificate for this run. The runner checks its served fingerprint and TLS version; normal untrusted clients must reject it. It verifies dashboard/security headers, anonymous denial, actual HTTPS sign-in, `Secure`/`HttpOnly`/`SameSite=Strict` test cookies, omission of those cookies over HTTP, authenticated research reads, viewer mutation denial, CSRF rejection, rejection of HTTP/foreign/API-port origins, secure logout and revocation of an older cookie. The HTTPS port does not serve plaintext HTTP. The fixture's AI workers and monitoring are disabled; no inference, tool generation or model evaluation is performed.

## Explicit runtime gate

The opt-in settings are `AIN_LOCAL_HTTPS=1`, `AIN_LOCAL_TLS_DIRECTORY` and `AIN_LOCAL_TLS_SHA256`. Both components require the native `test` profile, loopback routing and `AIN_SESSION_COOKIE=ain_test_session`; container mode, the ordinary session namespaces and unsupported flag values are rejected. The API additionally requires an explicitly selected private state directory beneath `.local` and its `ain.sqlite3`, preventing default-state fallback. The runner supplies these settings; the command is the supported way to exercise this mode.

The gateway loads only bounded certificate/key files in an unredirected private `.local` directory. It checks the external certificate pin, self-signature, matching RSA key, validity/lifetime, exact localhost/IP names and server/non-CA usage before listening. Failed loading produces a fixed error without certificate values or key bytes. [Certificate preparation](LOCAL_TLS_PREPARATION.md) additionally validates its unsigned manifest; the gateway does not use that manifest as an authority. Certificate renewal and Windows private-key ACL qualification remain open.

The API permits mutation origins only from the configured HTTPS gateway port in this mode. Login and logout cookie responses carry `Secure`; the gateway forwards the cookie to the API over plaintext **loopback** HTTP. This is not encrypted transport between separate hosts or protection from other local processes. No forwarded-proxy identity is trusted. The normal HTTP mode is unchanged, and public TLS/proxy settings remain rejected. There is no redirect or HTTP fallback for the test HTTPS listener, no HSTS claim and no public-certificate trust or managed identity qualification.

Focused checks:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_local_https tests.test_local_tls tests.test_configuration tests.test_june_http_rehearsal -v
npm.cmd run test:web
npm.cmd run check
```

Original-user browser access, representative load, full release qualification and all production acceptance gates remain separate work. Keep every generated certificate, private key, password and state file out of Git and public reports.
