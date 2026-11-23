# Generated-answer diagnostics

The offline evaluator now requests generated answers for every question in the unchanged 24-case development suite. It exercises the existing hybrid retriever, prompt, quotation-constrained schema and Qwen3:8b model. It changes no ranking, thresholds, prompt, source document, index, API, account or dashboard behavior.

## First recorded run — 23 November 2026

The [public report](reports/Generation_Diagnostics.json) retains every outcome, generated claim, exact supporting quote, passage location and pending review status. The actual local-model run took 42,118.35 ms; this is one sequential engineering run, not a deployment throughput or reliability measurement.

| Observation | Recorded result |
| --- | ---: |
| Questions processed | 24 |
| Retrieval unavailable | 0 |
| Generation unavailable or rejected | 2 |
| Completed answerable cases | 16 of 18 |
| Answers with nonempty claims | 16 |
| Structurally verified claims | 28 |
| Required gold quotes present in generated citations | 14 of 16 evaluable targets |
| Outside-corpus answer abstentions | 6 of 6 |
| Outside-corpus generated answers | 0 |
| Cases pending human semantic review | 24 |

Two answerable cases, `v2-alerts` and `v1-selection`, returned the service's combined `unavailable_or_rejected` status. The service does not expose which underlying cause occurred, so no narrower diagnosis is claimed. They are excluded from completed-answer denominators, never credited as correct abstentions. Four of the original 18 answerable targets lack a generated citation containing the gold quote: those two unavailable/rejected cases and `v2-splits`/`v1-rejection`. The run is explicitly **incomplete**. No retry or prompt tuning was performed to replace the first outcome.

Three outside-corpus cases abstained before generation because no evidence was retrieved; the other three returned a completed empty claim list despite retrieved passages. This differs from the previous retrieval-only report's three false retrievals. Answer abstention does not retroactively make those passages relevant.

## A concrete semantic failure remains

`v2-splits` asked for second-experiment training, validation and testing counts. The model instead claimed that its validation period was April 2025, citing a `MODEL_DATASET.md` table row that says **February 2025**. This passed the existing citation-ID, substring and numeric-token checks: the source quote exists and the number 2025 is present, but the month and experiment context are not supported. It also did not answer the requested counts.

`v1-rejection` gave reasons for model rejection but quoted only the instruction not to serve the candidate and a note about calibration/carrier slices. That cited quote does not itself establish the stated reasons. Both cases remain unchanged in the report, with human review pending. These source comparisons are maintainer observations, not an independently labeled semantic benchmark.

Consequently, **28 structurally verified claims does not mean 28 correct claims**, and 14/16 gold-quote coverage is not answer accuracy. Exact quote copying can miss valid paraphrases, reward irrelevant copying and overlook contradictory additional claims. A later change needs explicit experiment/version context, claim-level semantic review and a separately authored evaluation set. The current suite has already been inspected and must not be presented as an untouched test set.

## Integrity, failure handling and reproduction

The evaluator loads the existing label validator and confirms that every gold quote fits an indexed passage. Returned evidence must match that loaded passage's identity, text and line range. Generated claims are rechecked using the existing citation, quote and numeric validator. Unknown statuses, inconsistent modes, changed provenance or generation-model identity abort verification rather than receive success credit.

The report records source/index/suite fingerprints, corpus revision, both model digests and normalized source-code fingerprints. These identities are checked again after the run. Only the fixed public corpus fields and validated claims are projected; arbitrary response metadata, internal errors and passage vectors/text are excluded. Individual case results are flushed to an exclusive private progress journal. A crash or verification failure leaves that journal, including a sanitized failure type, for inspection; a missing final report never counts as a completed evaluation.

With the trusted existing index and both Ollama models available on loopback, choose a new private filename:

```powershell
.\.venv\Scripts\python.exe -m rag.generation_diagnostics --output .local/evaluations/generation-new-run.json
```

The CLI refuses paths outside this checkout's `.local`, existing reports and existing progress journals. Exit status 2 means the final report contains unavailable/rejected cases; inspect it rather than treating the run as a success. Preflight or integrity exceptions leave a failed journal and no verified final report. Model unavailability is distinct from a correct abstention. Do not overwrite this recorded first run or silently tune and replace it.

Eight synthetic tests cover explicit generation calls, quote/source checks, scope, privacy, unavailable/rejected versus empty answers, outside generated answers, contradictory citations/numbers, changing identities and durable exclusive output. The actual Ollama run is separate from CI fixtures. Human semantic review remains pending for all cases.

This is an offline evaluation milestone. The running dashboard remains on the preceding verified retrieval-panel build; no container update is necessary to inspect this public report or run the host CLI. All 64 workspaces, credentials, flight data and delay-v2 serving remain unchanged. All 24 production requirements remain open; no airline acceptance, security robustness or production qualification is established.
