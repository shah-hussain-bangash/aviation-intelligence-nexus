# Local sign-in and access roles

The connected research API now requires an authenticated session. The 64 prototype workspaces still use demonstration data and remain publicly browsable on the local page; they are not real privileged airline services.

## First account

From the project folder and its Python environment:

```powershell
python -m services.api.manage_users create --username shah --role admin
```

Enter and confirm a private password of 12–128 characters when prompted. It is hidden and must never be pasted into chat, source files or command arguments. Wait for the explicit account-created success message, then open http://127.0.0.1:8080 and sign in. There are no default accounts or default passwords. The first account must be an administrator. Restart the local services after installing updated dependencies or backend code.

Local OS owners can create additional accounts with the same command and `--role researcher` or `--role viewer`. To change access:

```powershell
python -m services.api.manage_users set-role --username analyst --role viewer
python -m services.api.manage_users disable --username analyst
```

Access changes revoke that user's sessions. The final active administrator cannot be disabled or demoted. These are local administrative CLI operations; remote account administration, self-registration, password reset and email verification are not implemented.

## Enforced permission matrix

| Capability | Viewer | Researcher | Admin |
|---|---|---|---|
| Read historical data aggregates and model reports | Yes | Yes | Yes |
| Calculate historical research scenarios | No | Yes | Yes |
| Review/export own saved runs | Yes | Yes | Yes |
| Review all local runs, including legacy anonymous records | No | No | Yes |
| Approve operational airline decisions | No | No | No |

Permissions and history ownership are checked on the server. Hiding the calculation button is not the authorization control. Old anonymous runs are preserved with a NULL owner and remain visible only to administrators. New saved runs record the authenticated username and owner ID. Request-key reuse across accounts cannot reveal another user's saved result.

## Implemented controls

- Argon2id password hashing with a random salt and explicit parameters; plaintext passwords are not stored. Existing hashes are upgraded on successful login when parameters change.
- Random session tokens in HttpOnly, SameSite=Strict cookies, scoped to `/api`. Only token hashes are stored in SQLite. Sessions expire after eight hours and can be revoked by logout or CLI access changes.
- Origin validation plus a session-bound CSRF header on state-changing API requests. The browser keeps the CSRF value in memory, never localStorage. No wildcard CORS policy.
- Five failed logins per normalized username in one minute trigger a 429 response. Unknown usernames use a dummy password hash and the same invalid-credential response.
- Session/role lookup on each protected request. Data endpoints return 401 without a valid session; viewer calculations return 403.
- The fixed local proxy forwards only the AIN session cookie, Origin, CSRF and request-key headers it needs. Other cookies and Authorization headers are filtered. Password bodies are not logged.
- Sign-out and expired sessions clear the connected panel and saved-result views. Prototype browser-local interactions remain separate.

## Limits

This is a tested **local development identity foundation**, not production security certification. Cookies use `Secure=false` only because the local app is HTTP on loopback. HTTPS with Secure cookies, managed identity/SSO, MFA, distributed rate limiting, hardened host/proxy policy, security assessment, recovery and operational monitoring remain outstanding. Do not expose these HTTP services to a network or public host. Local filesystem administrators can modify users, sessions or history; the log is not tamper-proof.

The data/model/operations caveats remain unchanged. Sign-in does not validate a research model for airline use. Development hosts default to `127.0.0.1` and `localhost` with ports 8080 and 8002; custom ports are taken from `PORT` and `AIN_API_PORT` at server startup.

References: [argon2-cffi password hashing](https://argon2-cffi.readthedocs.io/en/stable/howto.html), [API reference](https://argon2-cffi.readthedocs.io/en/stable/api.html).
