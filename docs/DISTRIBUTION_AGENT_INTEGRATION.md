# Recorded input evidence in investigations

In the Investigation desk, choose **Load input comparison**, then run the investigation with a researcher/admin account. The example explicitly requires the new `distribution_evidence` tool. Its checkbox consumes one of the existing three required-tool slots. Viewers can inspect their saved evidence but cannot submit or review runs. Other examples clear the new permission; ordinary old requests omit the false default and retain their serialized identity.

## Tool and retained evidence

The model sees this tool only when `include_distribution_evidence=true` and `required_tools` contains `distribution_evidence`. The server requires both together, a strict boolean, and empty tool arguments. It accepts no month override, SQL, file path or URL. The fixed source is the pinned January–March versus May input-comparison report; the monthly selector does not change these cohorts. This tool does not profile the database, invoke prediction or change an account, model or airline operation.

The saved snapshot contains both cohort sizes, all five TV/JS/unseen-category summaries, three largest absolute category-share changes per input, source/protocol fingerprints and the recorded limitations. Only bounded source text is sent back to the planner, not the full snapshot. Structured evidence remains visible/exportable even when a generated draft selects fewer source extracts. Server review recomputes canonical equality against the fixed pinned observation and blocks changed data, wording, arguments or permission. The browser additionally checks scope and arithmetic and withholds invalid snapshots.

Coverage acceptance also requires this entire exact source quotation:

> Retrospective marginal differences do not prove model degradation or causality, and matching counts do not verify frozen CSV identity; no live drift alert is available.

If omitted, the existing single bounded repair attempt requests it. A still-incomplete draft cannot be accepted as reviewed research; it can be marked needs changes. The original limits remain: three planner/tool calls, at most two summary attempts, cooperative 120-second budget, saved checkpoints, stop requests and exact-report human research review. This is a mechanically checked source-extract workflow; general semantic task completeness and independent approval are not established.

## Actual local-model check

`reports/Distribution_Agent_Integration.json` records an actual Qwen3:8b direct-runtime check using separate engineering checkpoints and the existing local provider. It completed in **12,491.13 ms**, selected the permitted tool, retained the canonical snapshot and produced three verified extracts: cohort sizes, the largest-TV comparison (weekday, 0.046677) and the required limitation. No repair was needed. It awaits human review. Reusing its request key reopened the saved result without another investigation. No real user account or operational action was used in this engineering check; it is not a held-out agent benchmark or a real-user authenticated browser execution.

Reproduce using `python -m agents.evaluate_distributions --output .local/new-distribution-agent-check` with local Ollama/Qwen3 available and no competing local investigation. The directory must be new. Requests/checkpoints/results remain private until the aggregate engineering evidence has been reviewed for publication. The workflow monitor recognizes the new tool; older monitoring snapshots show its category as not reported rather than inferring a zero.

Seven Python tests cover explicit permission/default compatibility, argument restriction, canonical snapshots/retry/review, bounded missing-limit repair, tamper/cached-quality rejection, source failure/lock release, queue deduplication and the new monitoring bucket. Three Node tests cover payload limits and saved evidence scope/arithmetic/escaping; the existing operations test covers old/new snapshot compatibility. Seven isolated component browser cases cover desktop, exact 390px mobile, tool bound, example resets, viewer access, input clearing, export and session clearing. They use actual recorded engineering evidence with simulated queue transport, without a real user session. See `reports/Distribution_Agent_Browser.json`.

Changing the pinned source or snapshot format requires an explicit version/compatibility review; current canonical validation intentionally rejects changed observations. Existing model/route evidence is preserved. The runtime is already part of release-state compatibility checks, so older rollback manifests need review after its change; no new rollback qualification is claimed.

The comparison remains retrospective US research with counts aligned to frozen populations but no verified CSV identity. It adds no live drift alert, model-error diagnosis, causal explanation, external worker failover or operational acceptance. All 24 production requirements remain open.
