# Release-readiness assessment

The signed-in dashboard now provides **What is ready, and what remains?** It covers all 24 original production requirement IDs, with a dated local-progress assessment, remaining work, acceptance criteria, dependencies, proposed responsible roles and public source evidence. Search, evidence filters, refresh and JSON export are implemented. This is a read-only maintainer assessment, not a sign-off workflow.

As assessed on **21 November 2026**, 23 requirements have recorded evidence of some local progress; final scope acceptance has no implementation acceptance evidence registered. The earlier assessment recorded 22; the isolated application rollback drill adds bounded local progress. **All 24 production requirements remain open.** The number 23 is not a completion count, score, percentage or independent acceptance claim. Evidence may cover only a narrow part of a requirement, such as local password sessions rather than managed identity/MFA.

## Evidence boundary

`infra/readiness.json` preserves the original IDs and records the assessment text and expected public evidence fingerprints. The authenticated API `/api/v1/research/readiness` checks the original baseline fingerprint and requirement coverage, allows only public Markdown/JSON evidence paths, and compares evidence fingerprints. Text is normalized to UTF-8 with LF line endings so Windows and Linux checkouts agree.

Missing/changed evidence becomes **Evidence unavailable**. Invalid scope, a changed baseline, malformed metadata or attempted production acceptance returns HTTP 503 without a readiness claim. Every requirement remains production-open. File integrity confirms that the recorded document/report is present and unchanged; it does not rerun the experiment, validate its conclusions, check current runtime health or independently inspect implementation. The separate service-monitoring and platform panels retain their own runtime scope.

Evidence links use the deployed source commit when the release supplies a valid commit ID; development builds link to `main`. The assessment exposes its date, file-check time and source revision. The evidence catalog and hashes live together in the source repository: they are not signed attestations or a tamper-resistant audit.

Responsible roles are proposed responsibilities, not claims that particular people have accepted ownership. Dependencies are sequencing aids, not proof those prerequisites are complete. Exports contain public scope/evidence information and no account credentials or research inputs. Refresh failure clears the prior displayed assessment.

## Historical report

The original `AIN_Completion_Report.json` is preserved unchanged as the **19 November 2026 artifact baseline**. Its old implementation counts predate the local backend, models, solver, identity, AI and recovery milestones. Both HTML copies and the in-app completion view now label that scope and direct readers to this assessment. Outdated global statements claiming no model or agent execution were corrected; synthetic workspace contracts remain clearly separated from connected research services.

## Updating the assessment

After a real implementation or new test result, review the affected requirement's local progress, evidence and remaining production work. Update fingerprints only after reviewing the actual source evidence; do not refresh hashes merely to suppress a mismatch. Preserve the 24 IDs and retain production acceptance as false until an independent acceptance process and its authority have actually been implemented. This milestone provides no button or API to mark production requirements accepted.

The full Windows suite has **366 tests: 279 Python and 87 Node**. Linux explicitly skips the Windows DPAPI provider test. Checks include complete scope, missing/tampered evidence, cross-platform line endings, unsafe paths/links, false acceptance rejection, authentication, filtering and proxy read-only behavior. Browser checks cover the signed-in local Docker dashboard and mobile layout. Hosted checks must be verified for the published commit. These checks do not establish production qualification.

The next engineering priorities remain an independently recoverable off-site backup/key plan, owned external alerts, durable background workers, deployment rollback, managed HTTPS/identity, representative security/load/accessibility reviews and cloud acceptance. The exact sequence depends on the intended deployment environment and approved data scope.
