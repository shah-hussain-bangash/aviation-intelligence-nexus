// Partial browser hardening for the existing loopback dashboard, not TLS or XSS qualification.
export const securityHeaders=Object.freeze({
  'X-Content-Type-Options':'nosniff',
  'X-Frame-Options':'DENY',
  'Content-Security-Policy':"frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
  'Referrer-Policy':'no-referrer',
  'Permissions-Policy':'camera=(), microphone=(), geolocation=()',
  'Cache-Control':'no-store'
});
