# Scoped Answer Lab

The dashboard now includes an opt-in **Scoped Answer Lab** for the source-coverage and context-excerpt research workflow. Open it from the connected-research toolbar. Select delay-v1 or delay-v2, enter a question, acknowledge the research limitations and submit. Example buttons fill a question without submitting it. Existing Q&A and all 64 workspaces remain available.

## User-visible behavior

The lab distinguishes cited excerpts, explicit-version clarification, source-vocabulary refusal, empty answer and unavailable/rejected generation. Missing vocabulary terms are shown so the researcher can inspect the selected source or revise the question. A valid paraphrase can still be refused; short unsupported topics can still pass coverage. No bypass or operational approval is implied.

Exact excerpts link to the recorded source revision and line range. Context addition is disclosed. JSON export includes only the verified query, outcome, public coverage/scope fields and excerpts. The user's question is included in their explicit download. Unknown response metadata, credentials, vectors, internal errors and model-service details are excluded.

No query or result is saved to research history or a new database table. Ordinary aggregate request monitoring remains in place. Downloaded copies are outside session clearing and cannot be recalled. Exported excerpts require relevance and semantic review; this feature does not establish production suitability or airline authority.

Inputs, acknowledgment and results clear on account changes. Editing the question/experiment clears the previous result, disables export and invalidates pending responses. Logout, failed validation, failed transport and late responses from previous queries/accounts cannot expose or restore a stale result. Browser cancellation withholds a result; it does not promise to interrupt an already running server/model call.

## API and access

`POST /api/v1/research/scoped-query` accepts exactly `question` (8–600 characters), `experiment` (`delay-v1` or `delay-v2`) and a strict boolean `acknowledged: true`. Extra fields and query parameters are rejected. The fixed dashboard proxy bounds the JSON body at 4 KiB and forwards only the scoped session cookie, origin and CSRF metadata to the configured local API. It has the same 100-second upstream deadline as existing Q&A.

Existing session, origin, CSRF and researcher/admin role checks apply before execution. Viewer and anonymous requests cannot invoke the workflow. The handler rechecks the current session and role before and after execution; revoked sessions or role loss withhold the result. The final boundary is not a transactional guarantee against a revocation racing after the final check. Errors are sanitized. Response projection checks request identity, coverage arithmetic, scope, source, line bounds and verbatim-claim identity before returning an allowlisted shape.

The underlying research workflow retains its own trusted-index/source validation, explicit scope guard, bounded source vocabulary, model/index checks and exact-excerpt construction. No model, prompt or retrieval experiment was retuned for the UI. Native scoring, original document Q&A, agent workflows, credentials and database schema are unchanged.

## Verification

Seven new Python tests cover request validation, public projection, admin/researcher/viewer access, origin/CSRF, session revocation during execution, sanitized failures, no database row changes and deterministic refusal branches without provider access. Three Node tests cover response/rendering/export validation and the bounded fixed proxy contract.

Thirteen isolated browser scenarios cover excerpts/citations/export, coverage refusal, a valid-paraphrase refusal, scope conflict, empty answer, unavailable generation, HTTP outage, invalid identity, input edits during a pending request, logout, account replacement, viewer restrictions and narrow layout. See [browser receipt](reports/Scoped_Lab_Browser.json). Transport/session states are simulated using the [public protocol fixtures](../tests/scoped_lab_fixtures.json); the success fixture derives from the preceding recorded model query. The narrow check reported an effective CSS width of 433 pixels, not coverage of every smaller device.

A separate [disposable authenticated native API drill](reports/Scoped_Lab_HTTP.json) exercised the actual trusted host index and local model for split counts, plus actual coverage refusal, scope clarification and the known valid-paraphrase refusal. All four returned their expected outcomes, and database table row counts were preserved. It used a temporary fixture account/database, never the primary user's account or password. Native API, component preview and container deployment verification are distinct evidence scopes.

Windows validation is 467 tests (364 Python, 103 Node). A running container must be rebuilt to serve the new API/component. The local deployment receipt is generated separately after the operator update, verifies the actual image source revision and preserves account/flight/model checks. Existing rollback receipts remain historical unless they match the newly running build and protected state contracts; this UI change does not create a fresh rollback qualification.

All 24 production requirements remain open. This is an explicitly labeled research interface for inspecting bounded local evidence, not independent semantic/security acceptance or a production airline system.
