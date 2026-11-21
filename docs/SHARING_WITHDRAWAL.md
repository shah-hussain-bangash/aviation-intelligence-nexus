# Pending report sharing withdrawal

In the Investigation desk, open an authored report that opted into second-account review and is still awaiting review. Enter a reason, check the confirmation and select **Withdraw sharing**. The saved report becomes `withdrawn`. It leaves the peer inbox and ordinary peer read access ends. The author and administrators retain inspection and JSON export, including the original request, tool observations, source extracts, exact report fingerprint and withdrawal receipt. Existing passwords and accounts are unchanged.

This ends future access through the pending-review policy; it cannot recall previously displayed or exported copies. An active administrator can also withdraw a pending shared report. An author downgraded to viewer retains this privacy action for their own report. Other researchers cannot withdraw it. No human review is invented, no report is deleted and no operational action is authorized. Completed decisions cannot be withdrawn through this control. There is no reopen/re-share operation; start a new investigation if needed.

## Transaction and uncertain responses

`POST /api/v1/research/agent-withdraw-sharing` requires authentication, allowed Origin and CSRF. Its strict input contains a UUID run ID, exact 64-character report SHA-256, UUID withdrawal key, 5–500-character reason and boolean `acknowledged: true`. Request fields outside this schema are rejected. The fixed web proxy limits the JSON request to 4,096 bytes and forwards only the configured session cookie.

Inside one SQLite immediate write transaction, the service rechecks stored ownership, current account activity/admin role, current HTTP session validity, pending opt-in state and the hash of request/steps/claims. It records the authenticated account identity, time, note, key and exact report hash without changing those evidence fields or the review history. Competing review/withdrawal transactions serialize: one terminal transition wins. Withdrawal cannot overwrite a completed decision, and a review cannot follow withdrawal. The receipt is local mutable state, not protected audit evidence.

An identical retry by the same account, key, reason and hash returns the original receipt with `withdrawal_replayed: true`; changed retries conflict. A timeout or error is displayed as unconfirmed. **Refresh this report** reconciles saved state, and an unchanged retry reuses its withdrawal key. Changing a report selection, input or session aborts and invalidates the old display request. An already received server write can still complete after the browser aborts; inspect the saved report to verify. A missing inbox entry alone is not proof of withdrawal.

The terminal state is supported by archive filtering and aggregate queue observations. Older observation fixtures lacking the withdrawn bucket show **Not reported**, not an inferred zero. No automatic expiry, notifications, retention/deletion policy or independent-person verification is provided. Default private and historical reports are not automatically shared or withdrawn.

## Verification and limits

`reports/Sharing_Withdrawal.json` records twelve passing authenticated in-process HTTP checks using disposable accounts and a seeded copy of public recorded evidence. No new model call, real-user account change, real-user withdrawal or copy recall occurred. Reproduce with `python -m agents.evaluate_withdrawal --output .local/new-withdrawal-check`; the private output directory must be new. No passwords, tokens or cookies are published.

Seven Python tests cover evidence persistence/restart, archive/aggregate state, owner/viewer/admin permissions, current-role/session checks, concurrent review versus withdrawal, exact retries, invalid states/integrity and strict authenticated HTTP behavior. Three Node tests cover eligibility/escaped notes, legacy observation compatibility, archive filtering and bounded fixed proxy writes. Ten browser checks use isolated recorded fixtures and simulated transport, covering desktop/mobile, peer restrictions, viewer-owner access, session/input invalidation, retry keys, decision conflicts and saved-state reconciliation. See `reports/Sharing_Withdrawal_Browser.json`.

The full Windows suite contains 325 tests (250 Python, 75 Node). Linux skips the Windows DPAPI provider case. The store contract changed; historical rollback evidence does not qualify this release. Distributed deployment/failover, governed identities, operational reviewer assignment and production acceptance remain outstanding. All 24 production requirements remain open.
