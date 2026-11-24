# Local foundation: configuration and secret-reference preflight

Run the read-only checks in the exact process environment intended for each service:

```powershell
.\.venv\Scripts\python.exe -m services.api.configuration
node scripts/check-environment.mjs
```

Exit 0 means the supported local configuration is syntactically consistent. Exit 2 means fixed diagnostic codes identify rejected settings. No secret values, raw paths or environment dumps are printed. The checker does not read secret files, connect to an application database, create accounts, start services or verify an existing runtime. Python import caches are not application state. It is not a general secret scanner or proof of secure deployment.

## Supported local settings

| Setting | Validation |
| --- | --- |
| `AIN_ENV` | `local` (default) or `test`. Production/staging profiles are intentionally unsupported until deployment controls exist. |
| `PORT`, `AIN_API_PORT` | ASCII decimal ports 1–65535; distinct web/API ports; defaults 8080 and 8002. Explicit empty values, whitespace and exponent notation fail. |
| `AIN_CONTAINER`, `AIN_AGENT_JOBS`, `AIN_MONITOR_ENABLED`, `AIN_OBSERVER_MOUNTED`, `AIN_INTAKE_OVERVIEW_MOUNTED` | Only `0` or `1`; absent values default to `0`. Mounted-metadata flags require declared container mode. |
| `AIN_BIND_HOST` | Loopback by default; `0.0.0.0` only with declared container mode. |
| `AIN_API_HOST` | `127.0.0.1`; the `api` service alias requires container mode. |
| `AIN_OLLAMA_HOST` | `127.0.0.1`; `ollama` and `host.docker.internal` require container mode. |
| `AIN_SESSION_COOKIE` | Existing `ain_session` or `ain_release_session` namespaces. Passwords and cookie behavior are not changed. |
| `AIN_STATE_ROOT`, `AIN_DB_PATH` | API: when both native overrides exist, the database parent must resolve to the state root. Provided paths must be nonempty local paths without control characters or URI/network-path syntax. Legacy native DB-only overrides remain supported. Container API paths must be `/app/.local/active` and `/app/.local/active/ain.sqlite3`. Gateway checks do not own or validate database paths. |
| `AIN_RELEASE_REVISION` | A full lowercase Git SHA, or the explicit development labels `working-tree` / `development-working-tree`. |

The API validates before project service imports and again before factory construction, so known-invalid settings fail before application database initialization. Typed flags and ports drive API worker/monitor and Origin configuration. The gateway validates before its HTTP listener is created. The native `dev:all` launcher checks before port probing or process creation, refuses container mode and uses the safe request-log configuration. Its existing default of enabling the child API worker remains; preflight output for a parent shell is not a runtime worker-status check.

Compose now forwards an explicit `AIN_ENV`; an empty or unsupported value is rejected instead of silently implying production controls. Fresh images include both checker commands, and CI runs them inside the API and gateway containers. Existing deployed services are not changed by this source work.

## Unsupported security and secret configuration fails explicitly

Local accounts still use the existing private password prompt and database password hashes. No inline environment secret or managed identity provider is required or implemented. `AIN_AUTH_PROVIDER` accepts only `local`. Configuring `AIN_SECRET_KEY`, `AIN_API_KEY`, `AIN_ADMIN_PASSWORD`, `AIN_JWT_SECRET`, `AIN_SECRETS_FILE`, or `AIN_DATABASE_URL` is rejected without opening a file or echoing its value. Protected backup-key handling is unchanged; this does not create a new key store or rotate credentials.

`AIN_PUBLIC_ORIGIN`, `AIN_COOKIE_SECURE`, `AIN_TLS_ENABLED`, `AIN_TRUST_PROXY` and `AIN_CORS_ORIGINS` are also rejected because the corresponding public-origin/TLS/proxy controls are not yet integrated. Merely declaring one of these settings must not imply HTTPS, secure production cookies or trusted proxy handling. Other unrelated environment variables are outside this check and are not dumped or certified. `.env` files are not automatically read.

These are application-environment guards, not network enforcement. Arbitrary Uvicorn CLI flags, published Docker ports, filesystem ACLs, actual mount identities, reverse proxies and cloud networks require separate process/deployment verification. A container flag is an operator declaration, not proof of isolation. Changing process environment after imports is not a supported hot-reconfiguration mechanism; restart a new controlled process for configuration changes. Trusted explicit API factory arguments remain available for isolated tests.

## Verification and remaining gates

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_configuration -q
node --test tests/test_environment.mjs
npm.cmd test
```

Tests cover local defaults, strict flags/ports, routing restrictions, container state contracts, native path consistency, secret-reference redaction, actual rejected API/gateway startup, CLI exit codes and factory revalidation. Managed identity/MFA, HTTPS termination, real secret-provider integration and rotation, managed database availability, runtime inventory and independent security acceptance remain incomplete. Both successful checker reports retain `production_ready: false`.
