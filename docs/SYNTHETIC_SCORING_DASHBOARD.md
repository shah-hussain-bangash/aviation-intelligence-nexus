# Synthetic Model Lab dashboard connection

25 November 2026. Research UI only; no deployment or automatic service activation.

The connected research panel now mounts a Synthetic Model Lab for admin/researcher sessions and preserves all 64 workspaces and the existing login. It loads the configured dataset/model context, requires an explicit acknowledgment, and submits the selected dataset ID with its observed catalog revision and model/input hashes. Nothing scores automatically. Default server startup remains unconfigured; the panel explains that state and disables scoring.

Two exact routes are added to the existing same-origin proxy: GET context and POST synthetic score. Wrong methods, arbitrary query controls, non-JSON writes and requests over the existing 4 KiB limit are refused. The proxy retains its existing session/CSRF forwarding, backend destination restriction, timeouts and response handling. It does not add path selection or catalog management writes.

The browser validates result/dataset/version/input bindings, finite bounded predictions, selection events and research-only flags before rendering. Results show delay minutes and the fixed baseline for at most 20 rows, plus the server-reported lineage fingerprints. The browser does not recompute or authenticate those fingerprints. Dynamic labels are escaped; predictions are not probabilities. There is no saved history or automatic export.

Changing dataset, refreshing, clearing, changing access or starting another request clears prior results. Session changes abort pending work and invalidate its response generation. Failure or malformed evidence clears results and context, requiring a refresh before retry. Disabling acknowledgment clears displayed results. Viewer/signed-out sessions hide the panel; server authorization remains the actual permission boundary.

Verification combines five new contract/proxy tests with browser checks against an isolated local harness. The harness uses the real panel, proxy and opt-in FastAPI scoring service with a disposable synthetic account and retained synthetic model. It injects the fixture session and request token server-side, without changing browser cookies or using the user's account. Browser checks cover successful scores/trace, backend failure clearing, unconfigured service, and access change during a delayed response. This is not evidence of a browser login journey or a deployed dashboard release. The screenshot explicitly identifies the harness. Existing backend role/CSRF/revocation tests remain required.

```powershell
node --test --test-name-pattern=synthetic tests/test_dashboard.mjs
npm.cmd test
```

The focused name filter also matches the earlier gate synthetic test. Browser verification used the default desktop viewport; small-screen CSS has not received device-size acceptance testing in this increment. Preview processes are owned and stopped by the task. Fixtures, credentials, private account/catalog state, screenshots and logs remain outside Git.

Actual deployment configuration, the complete authenticated browser journey, accessibility/device/load qualification, protected scoring history, real-data model validation and production acceptance remain open. The operational prototype workspaces and original historical predictor are unchanged. This change is stacked on the opt-in API and remains unmerged/undeployed.
