# Passage-level retrieval diagnostics

AIN now has a reproducible evaluation of its unchanged local document retriever against a TF-IDF-only diagnostic baseline. The 24 curated questions and exact source/quotation labels are in `rag/retrieval_cases.json`; measured results, every returned passage identity and all misses are in [the recorded report](reports/Retrieval_Diagnostics.json).

These questions were authored from the current six-document development corpus before the completed run. They are not independently labeled, held-out, representative airline questions or adversarial security tests. The existing eight-question demonstration remains historical and unchanged. The new evaluation generates no answers and makes no retrieval-weight, threshold, index, account or application changes.

## Recorded run: 23 November 2026

| Observation | Current hybrid retriever | TF-IDF-only baseline |
| --- | ---: | ---: |
| Available cases | 24/24 | 24/24 |
| Required passages found among the first three | 17/18 | 17/18 |
| Target recall at three | 0.9444 | 0.9444 |
| Mean target reciprocal rank at three | 0.7315 | 0.7963 |
| Correct abstentions on out-of-corpus questions | 3/6 | 2/6 |
| Out-of-corpus questions returning passages | 3/6 | 4/6 |

The completed local run took 2,322.64 ms. This is the elapsed evaluation, including embedding/service calls, lexical comparison and scoring. It is not a sustained-load or deployment latency result. An earlier attempt stopped on a model-service status timeout; that failure prompted explicit unavailable-case accounting. The completed run does not establish provider reliability.

Both methods found 17 required passages. Keyword search had the better reciprocal rank on this small set. Hybrid retrieval returned irrelevant evidence for fewer of the six out-of-corpus questions. Their abstention gates differ: hybrid uses its existing semantic and lexical gates; the baseline uses only the same lexical gate. This is not a threshold-matched comparison or evidence that one method is universally better.

The hybrid miss was the question about v2 training/validation/test counts; its returned passages did not contain the required labeled quote. Both methods returned evidence for unsupported questions about current Abu Dhabi runway wind, tomorrow's Etihad meals and hydraulic-pump repair. Returning a related passage does not mean the corpus answers those questions. No generated answer was requested or evaluated.

## Scoring and integrity

A relevant target must match both its declared source document and its exact quote inside one indexed passage. A document appearing somewhere in the results is insufficient. Each target receives its first matching rank from one to three, or zero reciprocal credit when absent. Target recall divides hits by available gold targets; mean target reciprocal rank averages `1/rank` over those same targets, with misses contributing zero. All-target coverage is also recorded for future multi-target cases.

Out-of-corpus cases count as correct abstentions only when no evidence is returned. A timeout or unavailable provider is recorded as unavailable, never as a correct abstention. Ranking/abstention metrics exclude unavailable cases and state their evaluated denominators. An incomplete run is explicitly marked incomplete, and metrics with no available gold targets are null.

Evaluation checks suite bounds, unique IDs, allowlisted sources, real source quotations and quotation placement in an indexed passage. It checks observed passage IDs, text and line ranges against the loaded corpus; rejects unexpected generation or contradictory modes; and verifies index/suite identity again after the run. The report preserves suite/index/source/model fingerprints, the corpus revision and per-case rankings. It exports no vectors, credentials, saved user questions or private error messages.

These checks establish the recorded comparison's mechanical provenance, not human semantic labels, answer entailment, comprehensive task completion, document permission enforcement, prompt-injection resistance or operational approval.

## Reproduce

Use the existing trusted index and installed `embeddinggemma:300m` model with Ollama running on loopback:

```powershell
python -m rag.retrieval_diagnostics --output .local/evaluations/retrieval-new-run.json
```

Choose a new filename; the command refuses an existing output and writes only beneath this checkout's private `.local` directory. Review results before deliberately publishing a sanitized report. Keep failed or incomplete runs visible. Do not silently revise labels, tune thresholds or rerun until a preferred score appears. A later retrieval improvement needs a separately versioned evaluation and an untouched independent test set.

Eight tests cover label validation, exact source/quote scoring, partial multi-target coverage, generation-disabled observed calls, unavailable-case accounting, changed passage/index rejection, privacy projection and denominator reconciliation. CI uses synthetic fixtures without Ollama or a GPU. The measured local-model run is recorded separately.

All 24 production requirements remain open. This phase adds engineering evaluation evidence, not a deployed dashboard feature or production qualification.
