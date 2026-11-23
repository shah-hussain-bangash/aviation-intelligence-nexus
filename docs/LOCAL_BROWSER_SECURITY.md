# Local browser response headers

The dashboard server applies one fixed header policy before routing. It covers successful pages/assets, health checks, proxied API responses and error/rejection paths. Existing backend destinations, cookies, CSRF checks, local origins and account credentials are unchanged.

| Header | Local policy |
| --- | --- |
| Content-Security-Policy | `frame-ancestors 'none'; object-src 'none'; base-uri 'self'` |
| X-Frame-Options | `DENY` |
| X-Content-Type-Options | `nosniff` |
| Referrer-Policy | `no-referrer` |
| Permissions-Policy | `camera=(), microphone=(), geolocation=()` |
| Cache-Control | `no-store` |

The framing policy prevents intentional iframe embedding of this standalone dashboard. The partial CSP restricts embedding, object content and base URLs. It does not restrict script/style execution and does not establish general XSS protection. Existing inline prototype behavior remains supported. The permission policy disables camera, microphone and geolocation features unused by this application. The referrer policy suppresses referrer URLs; it does not replace Origin/CSRF authorization.

The deployment remains loopback HTTP. These headers do not enable TLS, Secure cookies for a public HTTPS origin, managed identity/MFA, off-host monitoring or cloud deployment. Browser policy varies by client; HTTP integration checks establish returned headers and routing compatibility, not an independent browser/security audit. Direct internal API responses are outside this frontend-header scope. All 24 production requirements remain open.

`npm run test:web` exercises real isolated frontend/backend processes. It checks HTML, HEAD, modules, CSS, the login image and health routes, as well as malformed paths, missing files, rejected methods/content, invalid queries and backend failure. A synthetic proxied-login case verifies JSON and filtered session-cookie forwarding without real credentials. Existing API authentication/authorization tests remain separate.
