# Browser-local analyst self-review

The Scoped Answer Lab now offers **Review result** after a verified result is returned. This opens a browser-local assessment bound to that exact result. Existing plain result export remains available. Queries, reviews and notes are not uploaded or saved to research history; no backend route, database schema, credential or model behavior was changed for this milestone.

## Review states

For excerpts, the analyst records whether they checked the source, whether the result answers the question, and whether each excerpt is supported and relevant. Claim indexes and citation IDs distinguish multiple excerpts from the same passage. Notes are optional and limited to 2,000 JavaScript characters; notes and the original question are included in the explicit download.

| State | Meaning |
| --- | --- |
| Draft | Source checking or a required judgment is incomplete/uncertain |
| Self-reviewed · research only | The analyst asserted source checking and positive answer/support/relevance judgments |
| Needs revision | A completed excerpt assessment contains a negative judgment |
| Refusal self-reviewed | The analyst asserted that a refusal/clarification was appropriate |
| Refusal needs revision | The analyst marked a refusal/clarification inappropriate |
| Not evaluable | Generation was unavailable/rejected; notes cannot turn it into a successful answer review |

These are **self-assessments**, not verified semantic verdicts. No reviewer identity, independent review, airline authority or production approval is established. In particular, a model's result retains `human_review_complete: false`; a self-review does not overwrite that original service scope. Operational approval, independent review and production readiness stay false in the review envelope.

The source-check assertion is deliberately manual. Nothing prechecks it from citation syntax or an exact quotation. A valid source substring can still be irrelevant or incomplete. The earlier coverage false refusal and unsupported-topic blind spots remain real limitations of the underlying candidate.

## Exact-result and review binding

The export includes the allowlisted original result, analyst annotations, a canonical-result SHA-256 digest and a SHA-256 digest over the entire review payload. Canonicalization sorts object keys while retaining array order and literal values. Unknown response metadata is excluded before result binding. Fields and assessment labels are checked again before export.

The whole-review digest detects accidental changes to notes/judgments as well as result changes, unless the digests are deliberately recomputed. **These exports are unsigned and editable.** A person can create or recompute them. Hash verification does not prove authenticity, author identity, independent assessment, source truth or semantic correctness. The timestamp comes from an unverified client clock, not a trusted timestamp service.

Editing the question or experiment, clearing the query, logout and account replacement remove the review and all annotations. A new response starts unassessed even when its content matches a previous response. Reset assessment keeps the current result/digest but clears judgments and notes. Review-field changes or result changes during asynchronous hashing discard that pending export. Copies already downloaded cannot be recalled.

Drafts and negative findings can be exported; completion is not required to preserve useful feedback. Unavailable generation always remains not evaluable. Browser Web Crypto is required for digest binding/export; if it is unavailable, self-review export is disabled while the ordinary result remains usable. This workstation's loopback dashboard provides the supported local context.

## Offline consistency verification

After explicitly downloading a review, run:

```powershell
node scripts/verify-scoped-review.mjs "C:\path\to\AIN_Scoped_Self_Review.json"
```

The verifier reads one regular JSON file of at most 256 KiB, recomputes both digests and the declared assessment, and reports only consistency status, assessment and hashes. It does not print questions or analyst notes, contact a server, write a file or verify authorship. Changed, incomplete, oversized or unsupported artifacts receive a generic failure and nonzero exit. A valid draft verifies as a draft, not as an accepted answer.

## Verification evidence

Seven new Node tests cover canonical binding, complete/draft/negative judgments, refusal and unavailable outcomes, altered result/annotation/digest/approval fields, strict bounds, private-field exclusion and the actual CLI against unchanged/tampered files. Existing Node dashboard/startup tests still run through `npm run test:web`; the total is now 110 Node tests. Python remains 364 tests, for 474 local tests overall.

Fifteen isolated review browser scenarios cover draft/positive/negative annotations, refusal/clarification reviews, unavailable generation, reset, edits, logout, account replacement, viewer access, asynchronous result/annotation export races, altered artifacts and narrow layout. Twelve existing lab browser scenarios were also rerun. See [browser receipt](reports/Scoped_Review_Browser.json). These use public result fixtures and synthetic annotations; **no real semantic review was performed by the agent for this evidence**. The narrow layout reported an effective CSS viewport width of 433 pixels, not every smaller device.

The public response/export contract was extracted into a shared module without changing the backend API. No extra network request is made by reviewing, resetting, hashing or exporting. Source quotation/citation controls, current-role query access, stale-response clearing, all 64 workspaces and the original plain export are preserved. The Docker deployment receipt is generated separately for the exact published build after the operator update; browser fixtures alone are not deployment proof.

This adds a practical analyst checkpoint to a local research system. It does not close independent semantic/security acceptance or any of the 24 open production requirements.
