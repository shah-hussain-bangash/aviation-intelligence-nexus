# Model evidence investigations

The Investigation desk now offers **Load model review**. It selects recorded model evidence and an example objective; use **Run investigation** to submit through the existing owner-scoped background queue. Your account credentials and database schema remain unchanged. All 64 prototype workspaces are retained.

## Scope and contract

`include_model_evidence: true` explicitly permits and requires `model_evidence` in `required_tools`. The tool accepts empty arguments only. It cannot receive SQL, paths, arbitrary models, periods, URLs or operational actions. The field is strict boolean and omitted from serialized requests when false, preserving prior payload hashes and retry keys. The shared maximum remains three required/executed tools, three planner calls, two report calls and a cooperative 120-second budget. Other permitted unchecked tools remain optional; this is a bounded single-agent workflow, not a multi-agent platform.

The tool reads the same pinned public evaluation and permutation reports as the model diagnostics and input-reliance panels. It saves April/May records, errors, calibration, scores and prior comparisons; the April-only permutation sample/group summaries; both source report hashes; and their limitations. It does no inference, artifact deserialization, fitting, flight SQL or document-index update. Month/document selectors do not change these recorded model periods. No existing source experiment is rerun or overwritten.

The planner receives only bounded typed source text. The complete snapshot remains in the checkpoint, human-readable report and JSON export. This reduces unnecessary planning context. For opted-in model reviews, the planning instruction explicitly defers report writing to the separate summary step. A truncated provider decision still fails closed; token/time/tool limits are not relaxed.

## Review guards

Citation/exact-extract checks remain in place. The server also rebuilds the expected snapshot from the pinned reports and compares canonical JSON, including numeric/boolean types, provenance and evidence text. Changed metrics, source fingerprints, scope, arguments or source availability block research acceptance even if cached quality says passed.

A model-evidence draft must cite a source quotation containing **Input reliance is not causality or an individual-flight explanation.** Missing that explicit boundary blocks the coverage gate. The existing single bounded repair call may add the missing quotation; if it remains missing, acceptance stays blocked. This is a narrowly defined quotation requirement, not general semantic entailment or proof that every objective was answered. Human review still checks relevance, omissions, context and business applicability. No run is automatically reviewed or approved for airline actions.

The UI retains a separate structured evidence section even if the draft does not quote all figures. Scope/metric/mismatch failures withhold that section. Existing input/session clearing, owner history, report-bound review, retry replay, queue limits and queued-only cancellation remain. Viewers can inspect permitted saved reports but cannot submit or review new investigations. Loading route or synthetic examples resets model permission; loading a model example clears their requirements. Four required tools are rejected before submission.

## Actual local-model evidence

`reports/Model_Agent_Integration.json` contains a direct-runtime Qwen3:8b engineering run using isolated private checkpoints. It is not a real-user authenticated browser run, held-out benchmark, production load test or accuracy estimate. Its duration was 3,788.49 ms. The model selected `model_evidence`, generated two validated source extracts, passed the defined checks and replayed the same saved result on retry. The run remains awaiting human review, with operational approval false.

The retained extracts cover May metrics (597,574 eligible flights, 241,732 false alerts, 36,371 missed delays, 4.09% binned calibration error) and the non-causal limitation. Manual source inspection confirmed those quotations. The draft did not quote the April input-reliance result; the structured snapshot retains its five groups, sample scope and shuffle variability. **General objective completeness is not established.**

Development evidence is preserved: the first 9,469.87 ms run and a diagnostic repeat stopped after an overlong planner response. The diagnostic confirmed provider `done_reason=length`; no completed report was accepted. After bounded-context/planning changes, a 4,477.26 ms run passed the older mechanical gate but omitted the requested limitation. That omission motivated the explicit boundary check. These iterative development attempts are not a success-rate benchmark. No failed run is silently overwritten.

## Reproduce and verify

With the existing local Qwen3 model available:

```powershell
.\.venv\Scripts\python.exe -m agents.evaluate_model --output .local/new-model-review-check
npm.cmd test
```

The harness reserves a new private output directory, writes request/run/evaluation receipts and uses its own checkpoint database. It never signs into or writes research history in your real account. Do not publish its databases or local files. It verifies tool/snapshot execution, coverage, bounds, retry replay and awaiting-review state; these checks do not prove semantic completeness or API authentication.

The complete Windows suite passes 223 tests (178 Python, 45 Node); Linux skips the Windows DPAPI provider case. New tests cover opt-in/legacy serialization, forbidden arguments before execution, snapshot retention and planner projection, replay/queue identity, source failure redaction, altered metrics/text/scope, cached-review bypass attempts and bounded limitation repair. Node tests cover payload limits, saved snapshot rendering/withholding and escaped warnings.

Seven isolated browser component scenarios passed: desktop 1280, exact mobile 390, four-tool rejection, example reset, viewer access, input clearing, and session clearing with late responses. They use real component assets and the actual engineering report with synthetic queue transport, without a real user session. Export content and screenshots were inspected. This does not replace end-to-end authenticated browser, accessibility, concurrency or production qualification.

The new request/runtime contract requires compatibility review before using older protected rollback manifests. No new rollback qualification is claimed. All 24 production requirements remain open, including external workers, managed identity, independent recovery and operational acceptance.
