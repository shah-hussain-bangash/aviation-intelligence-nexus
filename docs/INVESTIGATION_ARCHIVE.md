# Searchable investigation archive

The Investigation desk retains its latest-updated ten-run shortcuts and now adds an **Investigation archive**. Search the objective, filter the run state, move to older pages or return to a previous page, then select a record to open its saved evidence above. The existing JSON export, role checks, stop controls and exact-report research review apply to the opened record. No investigation is started by browsing or opening an archive record.

## Read-only API

`GET /api/v1/research/agent-archive` accepts only `q`, `state`, `before` and `through`. Unknown/repeated parameters, invalid states, searches over 120 characters and out-of-range or inconsistent boundaries return HTTP 422. Search is a literal substring of the objective, with SQLite's ASCII case folding; `%`, `_` and quotes have no wildcard or SQL meaning. Non-ASCII text can match literally, but Unicode case folding is not provided.

Researchers and viewers see their own records; admins see all records. Authentication is required. Lists return only ID, objective, actor, state and creation/update times, ten records at a time. They exclude observations, claims, notes, request keys and submission aliases. Opening a selected ID uses the existing owner-checked run endpoint. An admin is allowed to inspect other owners' research, consistent with existing history permissions. This is not a new sharing or access-grant mechanism.

Pages order by insertion row ID descending, independently of updates. The first page captures an insertion ceiling (`through`); subsequent pages use `before` within that ceiling. Cursor values are exact decimal strings, including through the JavaScript proxy, avoiding 64-bit number rounding. These are query boundaries, not credentials: every request reapplies ownership and filters. No total-count scan is performed. New inserts appear after **Reload newest**. State changes and concurrent reviews can change filter membership; this is not a transactionally frozen archive snapshot. Reload after database restoration or maintenance that changes row IDs.

The connection uses SQLite `mode=ro`, query-only mode, a 250ms busy timeout and a cooperative three-second SQL/processing budget. Missing databases are not created. Lock, corruption and budget failures return a sanitized HTTP 503 without partial pages or private database errors. The fixed proxy accepts only reads and forwards only the configured session cookie. No unrestricted paths, SQL or URLs are accepted.

## Display and verification

Search/filter changes cancel or invalidate older display requests. Session changes clear metadata, controls and pending opens. Failure clears the previous page rather than showing stale results as current. The archive loads independently of model availability, so saved work can be browsed when the local generator is unavailable. The page state is observed when loaded; it is not live queue monitoring.

Seven Python tests cover owner/admin/viewer scope, traversal beyond ten records, metadata minimization, literal/state search, concurrent insertion/update boundaries, invalid queries, read-only missing/busy/corrupt databases, deadline failure and authenticated/sanitized API behavior. Three Node tests cover exact cursor/query handling, escaped metadata/scope validation and fixed proxy behavior. Six isolated browser scenarios cover desktop, exact 390px mobile, search/state/empty results, viewer open/export, outage/recovery and late-session clearing. Browser data and transport are synthetic; no real user's accounts or histories were used as test fixtures. See `reports/Investigation_Archive_Browser.json`.

This is bounded local research functionality. It does not provide full-text evidence search, immutable auditing, archive retention policy, multi-worker failover or production acceptance. All 24 production requirements remain open. No existing account credential, schema or report fingerprint is changed by this feature.
