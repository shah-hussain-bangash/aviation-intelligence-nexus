# Isolated browser session rehearsal

25 November 2026. Native test-mode isolation, not deployment or production acceptance.

The API and gateway admit the fixed cookie name `ain_test_session` only with `AIN_ENV=test` and no container mode. The gateway additionally restricts this routing to its loopback API host. Normal `ain_session` and `ain_release_session` behavior remains unchanged. No browser request can select a cookie namespace; it is trusted process configuration. Local/container startup rejects the test name, as does direct authentication-module import outside the supported test environment.

This permits an isolated test frontend/API to use the ordinary browser login form and real session cookie, rather than injecting a session or replacing the normal dashboard cookie. The proxy forwards only the configured test cookie and filters response cookies to the same namespace. It does not forward or replace normal native/release cookies in test mode. Test mode does not disable password, role, origin, CSRF, cookie HTTP-only/SameSite or logout checks.

Focused checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_configuration.py
node --test tests/test_environment.mjs
```

Two new Python cases verify configuration and fresh-process authentication import. Three new Node cases cover configuration/routing, actual gateway preflight and both incoming/outgoing cookie isolation. The complete regression suite remains required. Start API and gateway in separate native test processes with matching `AIN_ENV=test`, `AIN_SESSION_COOKIE=ain_test_session`, local ports and an explicitly private state/database directory. Synthetic scoring still requires explicit factory injection with reviewed dataset paths/hashes. Do not point a rehearsal at the user's database or real model.

The browser rehearsal used the actual frontend, proxy, API and login form on temporary ports with two disposable synthetic accounts. An admin logged in and scored eight retained synthetic examples; a viewer logged in and had no scoring panel/link; logout returned to the sign-in form and hid scoring. No fixture session was injected. The private database retained three successful sign-ins and three successful sign-outs, with zero sessions after cleanup. The normal account database and cookie namespaces were not used. Temporary services were stopped. Fixture credentials, private state, screenshots and logs stay outside Git.

The screenshot shows the actual dashboard with synthetic scores and its 64-workspace navigation. Screenshot capture required a document clip corrected for the browser's existing 90% zoom; the page, zoom and UI were not changed to produce the image. Blank preliminary captures were not used as proof. This is a local fixture-account browser journey, not the user's real-account journey or a deployed-release smoke check. Device-size/accessibility/load qualification, managed identity/MFA/HTTPS, protected histories and real-data quality remain open.

Changing `auth.py` changes its selected persisted-state source fingerprint, even though schema remains 8 and the session table is unchanged. Earlier restore/rollback records remain historical; they do not qualify this revision. A future release needs new final-revision recovery/rollback evidence. No normal startup, paid/cloud resource, running deployment, password or operational model was changed. Production acceptance remains open.
