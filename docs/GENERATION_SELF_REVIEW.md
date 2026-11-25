# Frozen generated-answer self-review

`python -m rag.semantic_review` prepares an offline review of the existing generated-answer diagnostic batch. It never calls an AI provider, re-runs generation, changes prompts or writes to the dashboard/database. The earlier scoped excerpt self-review remains separate: this command reviews the **batch generation report**, including its unavailable cases.

## Prepare and read

From the repository root, use the exact historical report bytes:

```powershell
.\.venv\Scripts\python.exe -m rag.semantic_review export --report docs/reports/Generation_Diagnostics.json --report-sha256 54405945c0cf3d809ae30481694f4336757829e0e3bd38a410d7a89c6504e648
```

The command prints a fresh private packet path, packet SHA-256 and annotations path under `.local/generation-review/<unique-case>/`. It checks the current suite, all six source document hashes, exact passage identities/line ranges, cited quotations and recorded case metrics. It refuses stale source bytes rather than silently rewriting the report to fit the current checkout. A checkout whose line endings differ from the recorded bytes may fail this check; use the exact original corpus bytes, not edited hashes.

Open `READ_ME.txt` for the questions, generated claims and retrieved context. `packet.json` also contains the full six source documents, original diagnostic report/model identities and case bindings. The packet is deliberately an offline file workflow; no new dashboard review panel or network service is claimed.

Edit **only `annotations.json`**:

- Enter a reviewer label. This label is an unsigned declaration, not an authenticated identity.
- Read the source context and set `source_checked` to `true` only after checking it.
- For each generated claim, rate `supported` and `relevant` as `yes`, `no` or `uncertain`. Check whether the evidence actually supports the wording, rather than merely containing the same quotation.
- Rate `question_answered` for generated answers, or `abstention_appropriate` for completed abstentions. Leave undecided judgments as `uncertain`.
- Preserve IDs, hashes, claim indexes, citations and the fixed `not_applicable` / `not_evaluable` values. Notes are optional and limited to 2,000 characters per case.

The initial packet has **22 pending evaluable cases and two not-evaluable unavailable/rejected runs**. No ratings are filled in by the tool. For example, the preserved `v2-splits` answer says April while its own quotation says February; the reviewer must judge support and whether the requested flight counts were answered. This maintainer observation does not supply a formal reviewer rating.

## Assess declared decisions

Use the paths and full packet hash printed by export. Choose a new output filename:

```powershell
.\.venv\Scripts\python.exe -m rag.semantic_review assess --packet .local/generation-review/<unique-case>/packet.json --packet-sha256 <printed-full-sha256> --annotations .local/generation-review/<unique-case>/annotations.json --output .local/generation-review/<unique-case>/assessment-01.json
```

Replace the angle-bracket placeholders before running. This command checks bindings and summarizes declarations; it does not judge answer meaning. All original cases and claims must remain present. An evaluable case remains pending unless a reviewer label, source check and every applicable yes/no decision are present. Any `no` makes the case `declared_needs_revision`; all yes makes it `declared_acceptable`. Unavailable outcomes always remain `not_evaluable`, never correct refusals or successful answers.

The summary records packet/report hashes, a canonical annotation hash and per-case dispositions. Outputs must be fresh files under private `.local`; overwrites, parent traversal and redirected paths are refused. Keep annotations and their packet together for later inspection. Do not publish personal reviewer notes automatically.

## Limits and checks

Hashes bind supplied bytes but do not authenticate the source report, packet author or human reviewer. An operator can create a different unsigned report and explicitly pin it; the command is not an approval authority. The summary always retains `human_identity_verified: false`, `independent_review: false`, `semantic_benchmark_accuracy_measured: false`, `operational_approval: false` and `production_ready: false`. It does not overwrite the original report's pending review fields, calculate benchmark accuracy, repair generated answers or close production requirements.

Focused check: `python -m unittest tests.test_semantic_review -v`. Tests use synthetic reviewer declarations and cover pending/negative/all-declared cases, unavailable-case exclusion, altered/missing bindings, source drift, strict JSON, file pins and private new-file output. The redirect test runs where the operating system permits fixture symlinks.

Run `npm test` for repository regression checks. Actual human assessment, independently checked judgments, a protected review store, dashboard integration and representative unseen evaluation remain open.
