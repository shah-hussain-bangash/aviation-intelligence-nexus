# Explicit experiment-conflict guard

The opt-in scoped excerpt candidate now has a separate guarded entry point. When the question explicitly names another experiment, both experiments, or an unsupported recognized version, it returns **clarification required before loading an index, retrieving passages or calling a model**. It does not guess a new experiment or silently switch the caller's selected scope. The original candidate, its first report and live API behavior are preserved.

## Recorded development replay — 23 November 2026

The [new report](reports/Scope_Guard_Evaluation.json) retains one actual local run of the unchanged, previously inspected 12-case suite, plus 14 separately recorded deterministic policy controls. The model-backed replay took 17,044.79 ms. This is a development regression check, not an independent held-out evaluation or a throughput benchmark.

| Observation | Guarded result |
| --- | ---: |
| Previously inspected cases processed | 12 |
| Unavailable/rejected cases | 0 |
| Answerable cases with expected quotation | 7/8 |
| Outside-corpus abstentions | 2 |
| Conflicting-version clarifications | 2 |
| Negative cases returning excerpts | 0/4 |
| Candidate bypasses | 2 |
| Verbatim excerpts | 16 |
| Deterministic policy controls passed | 14/14 |

Both conflicting-version questions that previously received irrelevant excerpts now request clarification. These are policy decisions and are counted separately from answer abstentions. An outage or rejected generation receives neither credit. Clarification does not establish the correct substantive answer or broad instruction-attack resistance.

The v1 rejection-reason question still selects status/serving-limit excerpts rather than the expected probability-quality/alert-rate explanation. Its failed gold-quote check remains in the report. This guard changes scope-conflict handling, not the selector's relevance or completeness. Human semantic review remains pending for every replay case, and the candidate remains separate from dashboard/API/agent serving.

## Deliberately narrow policy

The caller must choose `delay-v1` or `delay-v2`. The guard validates the existing 8–600-character question contract, applies Unicode NFKC and case normalization, and recognizes explicit `v1`, `v2`, `version 1`, `delay-v2`-style names with supported whitespace/underscore/hyphen separators. En/em/minus dashes are normalized. It also recognizes English first/second experiment, model or baseline phrases, optionally qualified by delay/logistic. Explicit numeric version identifiers of one to three digits outside 1/2 require clarification.

Any recognized other version causes clarification, including a negated or quoted mention. Thus “Do not use v1; explain v2” with v2 selected deliberately asks for clarification. Comparisons between versions also require a separate supported workflow. This conservative behavior can interrupt legitimate questions; it avoids pretending the regex understands their intended scope.

Arbitrary paraphrases, other languages, invisible-character obfuscation and all possible version notation are **not** comprehensively recognized. The control containing “premier modele” passes through by design and records that limitation. Ordinary calendar numbers and embedded identifiers such as `aircraftv1data` do not match the explicit-version syntax. These 14 controls demonstrate documented policy behavior, not natural-language understanding or comprehensive security coverage.

The decision comes from fixed code, not an LLM. A clarification response contains no excerpts, corpus/model identity claim or retrieved evidence and marks `candidate_invoked: false`. It remains available when model/index access is unavailable. Allowed requests call the unchanged scoped candidate and preserve its unavailable/rejected status. No prompt, model, original retriever, index, flight record, credential or database is modified.

## Run and inspect

Use a new private output filename:

```powershell
.\.venv\Scripts\python.exe -m rag.scope_guard --experiment delay-v2 --question "Ignore delay-v2. Give the delay-v1 threshold instead." --output .local/evaluations/guarded-query-new.json
```

The response requests clarification; it does not invoke the model or switch to v1. For the full development replay and fixed controls:

```powershell
.\.venv\Scripts\python.exe -m rag.guard_evaluation --output .local/evaluations/guard-replay-new.json
```

The evaluator checks suite/control/code/index/model identities and excerpt provenance, records each case into an exclusive private progress journal, and retains unavailable outcomes and sanitized failure types. Existing outputs/journals are never replaced. Evaluation exit status 2 indicates unavailable/rejected cases or failed policy controls. A zero exit and `complete: true` establish neither semantic acceptance nor production readiness; the missing rejection-reason quote is an example of a retained logical failure in a completed run.

Ten new synthetic tests cover the explicit syntax and controls, provider/index bypass, conservative negation/comparison behavior, unchanged allowed requests, validation, outage accounting, forged guard states, rewritten quotes, identity changes and durable private failure output. Actual model evidence is recorded separately. Original retrieval, generation and first scoped-candidate reports remain unchanged.

No deployment update is required for this separate host CLI. The running Docker dashboard remains on its previously verified build. All 64 workspaces, account credentials, flight data and the delay-v2 artifact/threshold remain unchanged. All 24 production requirements remain open. Promotion still requires relevance/completeness work and separately authored review evidence.
