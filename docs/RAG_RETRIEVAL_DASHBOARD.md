# Recorded retrieval dashboard

The signed-in research dashboard compares the frozen hybrid and keyword passage-retrieval evaluation. Open **Inspect RAG retrieval** from connected research. All three signed-in roles can read the same public evidence; this panel neither generates answers nor calls Ollama, queries flight records, retrains models or changes the index.

## Evidence and interpretation

The recorded evaluation contains 24 curated questions, including 18 answerable targets and six outside-corpus questions, against six documents and 31 passages. Both methods retrieved 17/18 targets. Hybrid correctly abstained on 3/6 outside questions, versus 2/6 for keyword retrieval. Hybrid's three false retrievals and one missed target remain visible. These are descriptive curated-suite results, not held-out accuracy, current service health or a security evaluation.

The method selector, issue/all/answerable/outside/unavailable filters and literal search expose case-level results, expected passage quotations and revision-bound source links. An unavailable query is excluded from relevance denominators and never counted as a correct abstention. The default issue view contains four hybrid cases; keyword has five. JSON export contains only allowlisted public evidence plus the selected method/filter/search scope, without credentials, private errors or arbitrary added metadata.

## Read-only contract

`GET /api/v1/research/retrieval-diagnostics` requires an existing authenticated session. Query parameters and writes are rejected. The dashboard proxy forwards the session cookie only to the fixed endpoint. The API reads bounded fixed report/suite files, normalizes UTF-8 line endings and verifies their pinned hashes, corpus provenance, case labels, passage identities, ranks, availability, scoring and aggregate arithmetic. Contradictory or missing evidence yields a sanitized unavailable response rather than cached success.

The browser independently checks report structure and arithmetic. Refresh clears old evidence immediately. Failed validation, service failure and logout clear results and disable export; aborted or late responses from an older account/session cannot replace newer results. Accounts, passwords, database schema, the delay-v2 artifact and its 0.17 threshold are unchanged.

## Verification and limits

Seven Python tests cover report integrity, scoring, authorization, no database writes and failure handling. Three Node tests cover rendering/filtering/export, contradictory evidence and the fixed proxy contract. Nine isolated browser scenarios cover desktop/narrow layouts, filters, viewer access, outage/recovery, invalid evidence, logout, account replacement and unavailable-query accounting. See [browser receipt](reports/Retrieval_Dashboard_Browser.json). Browser transport/session failure cases use fixtures derived from the public recorded report, without real accounts or primary-state changes. The narrow scenario reported an effective CSS viewport width of 433 pixels; it does not establish coverage of every smaller device.

Full deployment is a separate operator step. Source tests and isolated browser checks do not prove that an older running container serves this panel. A fresh local deployment verification receipt must identify the actual build. Existing rollback receipts remain historical unless they match that build and its protected state contracts.

This adds research inspection, not operational airline authority or production acceptance. All 24 production requirements remain open. The frozen evaluation, its misses, source documents and model behavior are preserved. See [evaluation methodology](RAG_RETRIEVAL_DIAGNOSTICS.md).
