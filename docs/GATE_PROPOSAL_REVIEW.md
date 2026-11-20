# Synthetic gate proposal review

The Gate Allocation Lab now supports a review step for newly computed, saved synthetic proposals. Compute a proposal, inspect its assignments and comparisons, enter a review note, acknowledge the synthetic scope, then select **Save research decision**. The two decisions are **Reviewed as research** and **Needs changes**. Neither applies an allocation or authorizes an airport action.

## Exact proposal and expiry

New saved proposals receive a SHA-256 fingerprint over their complete immutable result and saved identity/time metadata, including the scenario, assignments, baseline, solver provenance and review expiry. Derived view status, replay flags and the separate review receipt are excluded. The review window ends exactly 24 hours after the original save time. The stored table creation timestamp is checked against that saved timestamp; changing only the JSON time or expiry cannot extend the window.

Before recording a decision, the server validates the synthetic input contract, scenario fingerprint and proposal fingerprint, reruns the independent assignment checker for both candidate and baseline, and reconciles coverage/cost/objective with the encoded penalty. This rechecks feasibility and accounting, not a new proof of solver optimality or business value. The proposal must still be within its original review window. Clock inconsistency and malformed timestamps fail closed.

Older proposals remain readable as **Legacy proposal — review unavailable**. They are not silently backfilled with a fresh review seal/window; compute a new proposal to use this workflow. Expired intact proposals remain readable, but new decisions are blocked. A receipt committed within the window remains a historical decision after expiry.

## Transaction and authorization

POST `/api/v1/research/gate-review` accepts a UUID run ID, exact proposal hash, UUID review key, decision, note (5–1000 characters) and strict boolean synthetic acknowledgment. Unknown fields, false/coerced acknowledgments and unsupported decision values are rejected. Origin/CSRF checks apply. Only researchers/administrators can submit: researchers may review their own proposals, and administrators may review all. Viewers can inspect their permitted saved proposals but cannot create a decision. Self-review is permitted and explicitly labelled; independent approval/separation of duties is not claimed.

A SQLite immediate transaction checks and records at most one decision per proposal. The same reviewer, decision key, proposal hash, decision and normalized note replay the exact existing receipt, including after expiry; they do not create a new decision. Changed keys, notes or conflicting decisions are rejected. Concurrent competing decisions commit once. Failed/unconfirmed responses must be checked against saved history before retrying; unchanged UI retries reuse their decision key.

The receipt records the reviewer, decision/note, acknowledgment, UTC time, proposal hash and decision checksum. Scenario and creation metadata remain unchanged. Proposal/receipt hashes detect mismatches but are stored in the same mutable local database. They are not signatures, protected auditing, human-presence proof or protection against a privileged database administrator who can rewrite records and recompute hashes. Exports include actor/reviewer identity and notes, so real user exports must remain private unless deliberately shared.

## UI and failure behavior

The review form is tied to the displayed saved proposal. Changing scenario inputs, selecting another saved result, signing out or changing role invalidates pending UI responses and clears review input. Expiry disables/hides the decision form and explains that a new proposal is required. The server authoritatively rechecks the window at commit, regardless of client clock or button state. Invalid proposal integrity withholds displayed results, export and review controls. Legacy/expired proposals remain viewable within their declared scope.

A saved review updates the displayed receipt and history. The proposal JSON export includes the exact proposal, separate decision receipt and the review-view metadata returned by the server at load/save time. That view metadata is a snapshot, not an assertion that an exported pending window remains open later. No credentials are changed, no identity accounts are created by the feature, no schema migration is required and all 64 prototype workspaces remain.

The request body bound accommodates Unicode notes. Error responses distinguish authorization, missing proposal, changed/expired/conflicting review and unavailable persistence without exposing internal diagnostics. No operational write or background replay is introduced. The existing RAG source allowlist/index is unchanged; this new document is not automatically part of that corpus.

## Evidence

`reports/Gate_Proposal_Review.json` records an actual solve and proposal/decision/replay operation against a temporary synthetic store, with an engineering fixture reviewer. The five-flight scenario assigns 5/5 versus greedy 4/5 at cost 14 synthetic units. It is the designed research sample, not an airport performance or savings measurement. No real user account or live airline system was used.

The complete Windows suite passes 244 tests (193 Python, 51 Node); Linux skips the Windows DPAPI provider case. New tests cover sealed result preservation, exact expiry boundaries, old/malformed clocks, legacy handling, changed/recomputed invalid assignments, extended expiry and creation-anchor mismatch, receipt alteration, identical replay/conflicts, concurrent decisions, owner/role checks, strict acknowledgment, Origin/CSRF, safe failure, persistence, escaped notes and Unicode proxy bounds.

Seven isolated browser component scenarios passed: desktop 1280, exact mobile 390, unconfirmed-save retry key reuse, expiry blocking, scenario-input clearing, session clearing with late responses and viewer restrictions. The real components use a temporary actual-solver fixture with simulated HTTP transport; this is not a real-user authenticated browser test or an operational decision. Export content and screenshots were inspected.

## Release limits

Rollback compatibility now includes the solver, gate history and review contract files. Older captured manifests are conservatively rejected until the intended release pair is reviewed/re-captured and re-drilled. No new rollback qualification is claimed. All 24 production requirements remain open, including real operational data/constraints, protected audit, independent approval where required, managed identity and production release acceptance.
