# Source-context answer candidate

The opt-in research query can now preserve the source sentence immediately before a selected explanatory excerpt. This includes the previously missed reason for rejecting the v1 logistic model without letting the model rewrite that reason. Earlier candidates, prompts and evaluation reports remain unchanged. The live dashboard/API/agents still use the preceding verified implementation; this is a separate host CLI.

## What was tested

First, a versioned selector prompt distinguished explanations from status labels and prohibitions. Its [first actual 16-case run](reports/Direct_Excerpt_v2_First.json) is retained as a **failed improvement attempt**: it still missed the rejection-reason quote and returned irrelevant excerpts for a new unsupported coefficient question. No retries were used to replace that result. It found 9/10 expected answerable quotations, gave three outside abstentions and two conflict clarifications, and returned excerpts for one of six negative cases. All 14 existing version-policy controls passed. The sequential run took 30,790.36 ms.

The suite contains twelve already inspected regressions and four additional maintainer-authored reason questions, written before this run. The prompt was revised after viewing a known failure. These are development checks, not independently labeled or held-out accuracy evidence.

Next, a deterministic context transform was applied to those **saved selections**, using the same trusted index. Its [recorded replay](reports/Context_Excerpt_Replay.json) made **zero new generation calls**. Four excerpts gained bounded source context. Expected-quote coverage became 10/10, including the rejection explanation. The unsupported coefficient question still returned irrelevant excerpts; adding context does not repair that relevance failure. This is not 100% semantic answer accuracy.

Finally, one fresh composed Qwen3 query for the known rejection question was run once through the new wrapper. The [query result](reports/Context_Excerpt_Query.json) contains the explanation: probability quality was worse and the threshold created too many alerts. Both original model-selected quotes and enriched quotes are retained. The answer remains a set of source excerpts, with some redundant material; it is not an independently reviewed concise explanation.

| Observation | Prompt-only model run | Saved-selection context replay |
| --- | ---: | ---: |
| Development cases | 16 | Same 16 |
| Expected answerable quotes present | 9/10 | 10/10 |
| Outside abstentions | 3 | 3 |
| Explicit-version clarifications | 2 | 2 |
| Negative cases returning excerpts | 1/6 | 1/6 |
| Excerpts | 17 | 17 |
| New generation calls in replay | Not applicable | 0 |

Human semantic review remains pending for every case. The one fresh query is distinct from the saved-selection replay and establishes no general improvement rate or provider reliability. The original failure is preserved, rather than replaced with the context result.

## Mechanical context policy

English questions beginning with “why” or “explain”, or containing reason/rationale/explanation, qualify for context enrichment. This is a narrow presentation heuristic, not semantic understanding. Other questions keep their selected text.

Each selected quote is first checked against its cited trusted passage, source and line range. Text must equal the exact quote, with length 20–400 characters. For a quote occurring exactly once in that passage, the wrapper can prepend the immediately preceding sentence from the **same paragraph**. It retains the original quote in full, copies a contiguous source substring, and accepts the expansion only when the entire result fits within 400 characters. It never crosses a blank paragraph boundary, truncates an oversized expansion, rewrites source text or chooses among ambiguous repeated occurrences. Sentence boundaries use punctuation/whitespace heuristics, so abbreviations, markup and complex prose can limit or complicate context selection.

Source context can make a reason visible but can also add irrelevant material. Original selections are retained separately. It neither creates new evidence nor proves the excerpt answers the question. The previously implemented explicit-version guard still runs before index/model access for conflicts. Rejected or unavailable selection remains unavailable; context is not fabricated to fill an empty answer.

The replay verifies a pinned first-model-run report, recomputes its metrics and checks corpus identity before transformation. It rechecks baseline/index/code identity at the end. Its report explicitly states that no new inference occurred. The query wrapper also checks index identity around enrichment. All outputs are new private files; original public reports are preserved.

## Reproduce

One fresh opt-in research query, with Ollama and the trusted existing index:

```powershell
.\.venv\Scripts\python.exe -m rag.context_excerpts --experiment delay-v1 --question "Why was the first logistic model rejected for actionable serving?" --output .local/evaluations/context-query-new.json
```

Replay the frozen selections without model generation:

```powershell
.\.venv\Scripts\python.exe -m rag.context_replay --output .local/evaluations/context-replay-new.json
```

The earlier prompt-only version is independently reproducible through `python -m rag.direct_evaluation --output .local/evaluations/direct-v2-new.json`; it is not silently substituted for the enriched workflow. Existing reports/journals are refused. Do not present reruns of these inspected questions as an untouched test set.

Sixteen new synthetic tests cover the v2 selector contract and evaluation, source-only construction, provider rejection versus abstention, conflict bypass, changed identities, context boundaries and ambiguity, source tampering, preservation of original quotes and zero-generation replay. Model-backed evidence is recorded separately from CI fixtures.

The source-context workflow remains a research candidate: the unsupported coefficient answer, relevance/completeness review, language coverage and broader adversarial evaluation are outstanding. No account, credential, flight record, model artifact, prediction threshold, source document, index or database is changed. All 64 workspaces remain available. All 24 production requirements remain open; this work does not qualify the system for airline operations.
