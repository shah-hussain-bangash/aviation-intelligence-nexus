# Conservative source-coverage candidate

An opt-in wrapper now checks whether long content terms in a question occur in the selected experiment document before invoking the context-excerpt candidate. The previously unsupported question about individual logistic coefficients declines before any model call because `coefficient` and `optimizer` are missing from that source. It no longer returns unrelated regularization/status excerpts on this development check.

This is a narrow lexical safeguard, not a semantic answerability classifier. A documented valid paraphrase is refused, and short missing subjects can pass the check. The wrapper remains separate from the live dashboard/API/agents. Earlier code, model runs and failure reports remain unchanged.

## First measured development run — 23 November 2026

The [recorded report](reports/Source_Coverage_Evaluation.json) retains all 18 cases, missing/matched terms and outcomes from one local run. The suite contains the previous 16 inspected development cases plus two new probes: a valid paraphrase and a short unsupported subject. The run took 25,669.04 ms. The policy and vocabulary rules were set before this run; the cases are maintainer-authored and not independently labeled or held out.

| Observation | Result |
| --- | ---: |
| Development cases processed | 18 |
| Unavailable/rejected cases | 0 |
| Expected answerable quotes present | 10/11 |
| Valid answerable questions refused by coverage | 1 |
| Negative cases returning excerpts | 0/7 |
| Negative coverage refusals | 3 |
| Negative scope clarifications | 2 |
| Other negative candidate abstentions | 2 |
| Candidate bypasses, including the false refusal | 6 |
| Coverage policy controls passed | 12/12 |
| Existing scope controls passed | 14/14 |

All original ten answerable cases retained their expected quotation, including the rejection explanation. The new question “What was the probabilistic assessment of the first model outputs?” was refused because `probabilistic` does not occur literally in the source, even though the source discusses probability quality. This is a retained **false refusal**, not a successful answer.

The coefficient question, aircraft-repair question and internal bin-byte question received source-coverage refusals. Two conflicting-version requests received clarification. The wind and spare-tire questions received ordinary candidate abstentions. These mechanisms are reported separately; the JSON field `negative_model_abstentions` denotes the existing candidate workflow's empty answer, which can include retrieval with no evidence, and does not establish that a chat-generation call occurred. Provider failures receive none of these credits.

Zero negative excerpts and 10/11 quote coverage on these inspected development cases do not establish general correctness, semantic entailment or security acceptance. Human semantic review remains pending for all cases. A completed run is not a production certificate.

## Exact policy and its limits

The explicit-version guard runs first. A recognized conflict requests clarification without accessing an index. Otherwise the trusted index loads and all passages from the selected fixed document form its coverage vocabulary. The model has not been called at this stage.

The policy applies Unicode NFKC and case normalization, extracts ASCII English letter tokens, removes scikit-learn's English stop words and a fixed small list of generic question words, and applies simple plural reductions (`ies` to `y`, or trailing `s` except `ss`, for words longer than five letters). The generic list is visible in `rag/source_coverage.py`, including `selection`; this is a hand-authored engineering rule, not learned vocabulary selection.

Only resulting question terms of at least eight characters are required. Any required term missing from the selected document triggers a no-excerpt `source_coverage_declined` result. The result records the required, missing and matched terms plus the normalized vocabulary fingerprint. It identifies a vocabulary mismatch rather than asserting that a human could never answer the question. A refusal does not contain invented model identities, retrieved passages or claims.

Important limits are explicit in the controls:

- A valid synonym or paraphrase can be refused. No broad lemmatizer, synonym model or multilingual parser is used.
- A short absent topic such as “crew cost” has no required long terms and can pass coverage.
- A source can contain a term while explicitly saying the requested fact is undocumented; word presence does not prove an answer exists.
- Non-English text may contribute no parsed terms and can pass to the existing candidate. This is not multilingual support.
- Corpus contamination with matching words can defeat lexical absence checking. This is not comprehensive instruction-attack protection.

Allowed requests use the unchanged context-excerpt candidate and preserve its failure status. Index identity is checked around the wrapper. Missing/stale index or changed evidence is an integrity/unavailable condition, never credited as a correct refusal. The evaluation also checks suite/control/code/index/model identities, validates every returned excerpt and flushes each result to a new exclusive private progress journal. Raw provider errors, vectors, credentials and private user records are not included in the public fixed-suite report.

## Reproduce

Known unsupported query, choosing a new private filename:

```powershell
.\.venv\Scripts\python.exe -m rag.source_coverage --experiment delay-v1 --question "Why did the optimizer choose each individual logistic coefficient for the first model?" --output .local/evaluations/coverage-query-new.json
```

Full development evaluation:

```powershell
.\.venv\Scripts\python.exe -m rag.coverage_evaluation --output .local/evaluations/coverage-evaluation-new.json
```

An existing output or progress journal is refused. Evaluation exit status 2 indicates unavailable/rejected cases or failed coverage controls; a zero exit does not certify semantic success and can coexist with the recorded false refusal. Model-backed evaluation is separate from synthetic tests and the additional real check with model routing deliberately disabled for the known coverage refusal.

Ten new synthetic tests cover vocabulary rules and tradeoffs, index/provider bypass order, allowed failure preservation, identity changes, separate refusal/clarification/abstention accounting, forged decisions, source provenance and durable private failure output. The running Docker dashboard, all 64 workspaces, accounts, flight records, index and delay-v2 artifact/threshold are unchanged. All 24 production requirements remain open. Broader labeled relevance review and a deliberate user experience for refusals are still needed before promotion.
