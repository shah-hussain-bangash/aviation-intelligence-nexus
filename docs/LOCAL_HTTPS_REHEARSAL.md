# Isolated authenticated HTTPS rehearsal

This connects the normal Node dashboard gateway and Python API through an explicitly enabled native test mode. It uses a fresh private database, separate test cookies, temporary synthetic accounts and a newly generated pinned localhost certificate. It does not convert the running dashboard, install operating-system/browser trust, create cloud resources or qualify a public service.

From the project folder:

```powershell
.\.venv\Scripts\python.exe -m infra.local_https_rehearsal --output .local/NEW_HTTPS_RUN
```

Default loopback ports are 18176 (HTTPS gateway) and 18177 (API); `--web-port` and `--api-port` accept two distinct free unprivileged ports. Existing output, redirected paths and occupied ports are refused before creating state. The runner generates private TLS files, seeds disposable admin/viewer accounts, starts its own gateway/API processes, performs authenticated requests and stops only those processes. Random passwords, session cookies and CSRF values are not saved in the result. Logs, private test state and `evaluation.json` remain under the new directory. This is a transport/API exercise, not a browser journey with the original user's account.

## Encrypted API connection and certificate recovery

Add `--encrypted-api` to encrypt both local connections:

```powershell
.\.venv\Scripts\python.exe -m infra.local_https_rehearsal --encrypted-api --output .local/NEW_ENCRYPTED_API_RUN
```

This explicit mode enables `AIN_LOCAL_API_HTTPS=1` alongside the existing native-test HTTPS gate and starts Uvicorn with the private certificate/key. The gateway verifies the backend through a dedicated HTTPS client with the explicit certificate trust, normal hostname checks, a hard certificate fingerprint check and TLS 1.2 minimum. It does not disable verification or install general trust. Every request uses a fresh agent, so a pooled connection or cached session cannot avoid the certificate check. Redirects are refused, responses are limited to one MiB and existing request deadlines are enforced. Default gateway-to-API HTTP remains available when this option is absent.

The encrypted runner records the distinct `ain-local-https-api-rehearsal-v1` format. It verifies the backend's served certificate and separately tests a wrong fingerprint even with a trusted certificate. It then stops only its own API and restarts it with a different self-signed certificate. A separately trusted diagnostic client confirms that backend is running, while the original gateway must return 503 for readiness and proxied reads. The frontend stays available. Restoring the original backend certificate must restore readiness and a new authenticated read. No original model, account or deployed service is fault-injected.

This test reuses a single short-lived loopback certificate/key across both processes. It establishes neither distinct managed service identities nor mutual TLS, remote private networking, public certificate trust or cloud deployment. No renewal or operating-system trust installation is performed.

Clients explicitly trust the generated certificate for this run. The runner checks its served fingerprint and TLS version; normal untrusted clients must reject it. It verifies dashboard/security headers, anonymous denial, actual HTTPS sign-in, `Secure`/`HttpOnly`/`SameSite=Strict` test cookies, omission of those cookies over HTTP, authenticated research reads, viewer mutation denial, CSRF rejection, rejection of HTTP/foreign/API-port origins, secure logout and revocation of an older cookie. The HTTPS port does not serve plaintext HTTP. The fixture's AI workers and monitoring are disabled; no inference, tool generation or model evaluation is performed.

## Explicit runtime gate

The opt-in settings are `AIN_LOCAL_HTTPS=1`, `AIN_LOCAL_TLS_DIRECTORY` and `AIN_LOCAL_TLS_SHA256`. Both components require the native `test` profile, loopback routing and `AIN_SESSION_COOKIE=ain_test_session`; container mode, the ordinary session namespaces and unsupported flag values are rejected. The API additionally requires an explicitly selected private state directory beneath `.local` and its `ain.sqlite3`, preventing default-state fallback. The runner supplies these settings; the command is the supported way to exercise this mode.

The gateway loads only bounded certificate/key files in an unredirected private `.local` directory. It checks the external certificate pin, self-signature, matching RSA key, validity/lifetime, exact localhost/IP names and server/non-CA usage before listening. Failed loading produces a fixed error without certificate values or key bytes. [Certificate preparation](LOCAL_TLS_PREPARATION.md) additionally validates its unsigned manifest; the gateway does not use that manifest as an authority. Certificate renewal and Windows private-key ACL qualification remain open.

The API permits mutation origins only from the configured HTTPS gateway port in this mode. Login and logout cookie responses carry `Secure`. Without `--encrypted-api`, gateway-to-API traffic is plaintext **loopback** HTTP; with it, that hop uses the pinned HTTPS client above. Neither mode qualifies a network between separate hosts or protection from other local processes. No forwarded-proxy identity is trusted. Normal HTTP defaults are unchanged, and public TLS/proxy settings remain rejected. There is no redirect or HTTP fallback for the test HTTPS listener, no HSTS claim and no public-certificate trust or managed identity qualification.

Focused checks:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_local_https tests.test_local_tls tests.test_configuration tests.test_june_http_rehearsal -v
npm.cmd run test:web
npm.cmd run check
```

Original-user browser access, representative load, full release qualification and all production acceptance gates remain separate work. Keep every generated certificate, private key, password and state file out of Git and public reports.
