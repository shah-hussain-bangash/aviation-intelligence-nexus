# Evidence-grounded regression review agent

Open **Investigation desk → Load regression review → Run investigation** after signing in as a researcher/admin. The local Qwen3 agent can now retrieve the frozen negative delay-duration experiment, select exact source extracts and save a report with the full April/May evaluation. Review/export, peer-sharing opt-in and sharing withdrawal retain their existing rules. **The regression model still failed its research check; this workflow neither retrains nor deploys it.** All 64 workspaces and existing credentials are preserved.

## Explicit permission and bounded tool

The strict boolean `include_duration_evidence` defaults to false and is excluded from serialized requests when false. Existing request identities, retries and default tool sets remain unchanged. Setting it true requires `duration_evidence` in `required_tools`; requiring the tool without permission is also rejected. It occupies one of the existing three tool slots. **Load regression review** clears unrelated requirements, route, simulation and sharing opt-ins; other examples clear duration permission. A viewer can inspect their saved report but cannot start investigations or record reviews.

`duration_evidence` accepts only an empty argument object. The model cannot choose a period, SQL, URL, file, artifact, target, hyperparameter or write operation. The implementation calls the existing fixed, hash-verified aggregate loader. It performs no flight query, deserialization, scoring, model fitting or policy change. This tool version requires the recorded failed research check; a different source/result requires an explicit version/compatibility review.

The saved snapshot retains the complete public duration evaluation: protocol/source/artifact/freeze identities, split populations, mean/median baselines, all April/May metrics, signed residual counts, severe-delay cohorts and limitations. Only bounded source text is returned to the planner. The full structured evidence remains readable/exportable even when an extract draft omits other details. These fixed cohorts are independent of the investigation's month, route and document selectors. The document RAG corpus remains the existing six approved project documents; this tool is not expanded aviation-manual ingestion.

## Mandatory findings and human review

Coverage acceptance requires exact quotations bound to the duration tool's citation for all three subjects:

1. May model RMSE/MAE versus the training-mean/training-median baselines.
2. Errors among the observed May delays of at least 60 minutes, including their retrospective cohort size and bias.
3. The full failed-check, non-deployment and already-inspected-release limitation:

> The duration model failed the preset 1% RMSE improvement check in both April and May; duration inference is not deployed. This already inspected US release is not a fresh holdout, causal explanation or operational approval.

Server review recomputes canonical equality of the entire saved observation with the pinned tool output, explicit permission, empty arguments and each required citation/quotation. Changed numbers, source wording, scope or cached `quality.passed: true` cannot bypass that check, even if the changed report hash is resealed. A missing quotation uses the existing single bounded repair attempt; still-incomplete drafts cannot be accepted as reviewed research. They can be marked needs changes. Missing/corrupt source evidence produces no fabricated snapshot. The browser validates the retained evaluation and withholds incompatible/changed evidence; review warnings name missing quotation subjects.

The limits remain three tools, three planner calls, at most two summary calls and a cooperative 120-second budget. Reports publish verified source wording rather than unverified generated paraphrases. These are mechanical coverage/citation checks, not general semantic accuracy, independent-person approval or a root-cause diagnosis. The agent has no weather or intervention evidence and cannot establish why the model underperformed, propose an authorized airline action, promise business benefit or treat a human research review as approval of the regression model. The classifier's existing artifact and 17% threshold are unchanged.

## Actual local-model evidence

`reports/Duration_Agent_Integration.json` records a real **Qwen3:8b** direct-runtime development check with separate engineering checkpoints. The final run completed in **8,408.83 ms**, selected the permitted tool, retained the canonical full evaluation and returned all three required quotations without repair. It awaits human review. Reopening the same request key replayed the saved result. All nine engineering checks passed, including the negative result, required quotations and no operational approval. An earlier 11,619.91 ms development run also selected those three extracts before the stricter three-subject review requirement was finalized; it is retained privately. These development runs are not a held-out agent benchmark or proof of general task completeness.

The extracted figures remain the earlier measured negative result: May RMSE 55.669319 minutes versus 56.171814 for the mean baseline; MAE 23.191613 versus 18.162460 for the median baseline. Among 52,142 observed severe delays, MAE was 124.546406 minutes and bias -124.543778 minutes. No duration model was fitted, rescored or selected during the agent checks, and no actual user account/review or operational action was used. Provider name/digest, tool trace, bounds, quotations and research scope are retained in the report. The primary dashboard's user state is not used for these direct-runtime checks.

Reproduce with `python -m agents.evaluate_duration --output .local/new-duration-agent-check` while local Ollama/Qwen3 is available. The output directory must be new. Requests/checkpoints stay private until sanitized evidence has been reviewed. This is a local single-agent workflow, not distributed worker orchestration or a multi-agent platform.

## Verification and remaining work

Seven new Python tests cover default identity/strict opt-in, the three-tool limit, argument rejection before source reads, canonical snapshot/retry/review behavior, each missing required quote and bounded repair, resealed/cached-quality tampering, source failure/lock release, queue deduplication and monitoring counts. Three Node tests cover payload bounds, retained evidence/escaping/withholding and legacy/current monitoring buckets. Nine isolated browser scenarios use actual recorded engineering evidence with simulated queue transport: desktop, exact 390px mobile, tool bound, example resets, viewer restrictions, input/session clearing, missing quotations and changed snapshots. Export construction and human-review controls are checked. See `reports/Duration_Agent_Browser.json`; no real user session is used in preview QA.

The monitoring panel recognizes `duration_evidence`. Older snapshots lacking this tool show **Not reported**, not an inferred zero. The full Windows suite has **356 tests: 272 Python and 84 Node**. Linux skips the Windows DPAPI provider case.

The runtime is an existing protected release-state contract. Historical rollback evidence does not automatically qualify this changed release. Broader semantic evaluation, approved aviation documents, causal/operational validation, distributed orchestration and production acceptance remain outstanding. All 24 production requirements remain open.
