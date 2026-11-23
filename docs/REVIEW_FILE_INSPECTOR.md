# Local self-review file inspector

The Scoped Answer Lab now includes **Reopen an exported self-review**. Choose a JSON file previously exported by the analyst self-review feature. The dashboard reads and verifies it locally, then displays the original question/result, recorded judgments, notes, source revision and artifact digests. It makes no model request and does not upload the file or save it to research history.

Imported files are explicitly labeled **unsigned local artifacts**, not new model responses. Loading a file never fills or replaces the current question, live result or its assessment. You may inspect an artifact while editing another question; the imported question remains separately labeled. Use **Clear imported file** to remove that display and release the widget's references. It does not delete the original file or downloaded copies, or promise secure memory erasure.

## Validation and display

The inspector accepts exactly one nonempty file of at most 256 KiB. Size is checked before reading and against the returned byte buffer. Bytes must decode as strict UTF-8 and parse as JSON. Both result/review digests and the declared self-assessment are recomputed through the existing verifier before any imported content is displayed. Question length is now checked at the shared review boundary against the original 8–600-character service contract. The offline CLI uses the same strict UTF-8 decoding.

Malformed files, changed notes/results/digests, unsupported flags, excessive size, invalid encoding and unavailable digest computation clear prior imported content and show a generic failure. A replacement selection clears the prior display immediately. Later completion of an older file read, Clear, logout or account replacement cannot restore that content. A pending byte read may still finish; its stale result is withheld.

Questions, excerpts, notes and filenames are treated as text. Notes are not rendered as HTML, instructions or links. Source links use the fixed repository, allowlisted document and recorded revision from the verified artifact shape. No imported question is automatically submitted to the API. The sign-in callback clears the inspector on account changes and disables its chooser for viewer/signed-out sessions; this UI behavior does not authenticate the author of a file someone selected locally.

## What verification means

Draft, positive, needs-revision, refusal and unavailable labels retain their original self-assessment meanings. The display says **Content consistency checks passed**, not that an answer is semantically correct. Hashes remain unsigned and can be recomputed by anyone. They do not verify author identity, independent review, source truth, operational approval or production suitability. The timestamp is explicitly an unverified client-clock value. Original service semantic review remains pending.

The inspector is read-only. To create another assessment, use the normal live-query review workflow; importing an artifact does not convert it into a current authenticated query or editable review. This avoids silently mixing imported judgments with a newly returned result.

## Verification evidence

Four new Node tests exercise real `File` parsing, pre-read byte bounds, strict UTF-8, buffer-size mismatch, altered files, question bounds, safe rendering, retained assessment states and the offline verifier's encoding boundary. Existing tests for review digests, stale export behavior, the dashboard and startup remain enabled. Local validation is 478 tests: 364 Python and 114 Node.

Twenty-three inspector browser scenarios passed, including draft/positive/negative/refusal/unavailable artifacts, literal unsafe text, file replacement, Clear/logout while reading, malformed/oversized/invalid-encoding/tampered input, crypto failure, account replacement, independent live-query editing, a simulated live response, viewer gating, a real local file chooser and narrow layout. Six existing query/review scenarios also passed. See [browser receipt](reports/Review_Inspector_Browser.json).

The browser evidence uses public result fixtures and synthetic notes, not private files or real analyst verdicts. The real chooser loaded an agent-created public draft fixture. The narrow check reported an effective CSS viewport width of 433 pixels; it does not establish coverage for every smaller device. No new model experiment was run for this feature.

Deployment verification is a separate exact-build receipt, produced after rebuilding the saved Docker dashboard. It verifies packaged file parsing/rendering and rejection of an altered review, alongside the existing account/flight/model preservation checks. Fixture browser tests alone are not deployment proof. All 64 workspaces, credentials, raw data, index, model artifacts, prediction threshold and database schema are preserved. All 24 production requirements remain open.
