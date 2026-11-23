# Experiment-scoped excerpt candidate

An opt-in host CLI now requires an explicit `delay-v1` or `delay-v2` experiment. Retrieval is restricted to the corresponding fixed public experiment document. Qwen3 selects at most three excerpt IDs; final answer text is constructed verbatim from verified source quotations rather than model-written paraphrases. This addresses two mechanical causes of the earlier April/February citation mismatch: mixed experiment documents and rewritten claim text.

This is a research candidate, separate from the existing API, agents and dashboard. It has **not been promoted** to live use. Source scope and exact copying do not establish question relevance, completeness or resistance to conflicting instructions.

## First candidate run — 23 November 2026

The [recorded report](reports/Scoped_Answer_Candidate.json) preserves the first actual Qwen3 run over the [12-case development suite](../rag/scoped_cases.json). The suite was authored before this candidate run. It includes two already-known regression questions, six additional answerable questions, two outside-corpus questions and two conflicting-version requests. It is maintainer-authored and not independently labeled or held out. The caller-supplied experiment is additional context absent from the previous unscoped evaluation, so the scores are not a matched improvement comparison.

| Observation | Recorded result |
| --- | ---: |
| Challenges processed | 12 |
| Unavailable/rejected cases | 0 |
| Answerable cases with the expected quote | 7/8 |
| Negative cases that abstained | 2/4 |
| Negative cases returning excerpts | 2/4 |
| Verbatim excerpts | 18 |
| Excerpts outside the selected document | 0 |
| Sequential elapsed time | 25,923.62 ms |

`complete: true` means all cases produced an observed selection/abstention outcome, **not** that all challenges passed or the candidate was accepted. All semantic reviews remain pending. Eighteen verbatim excerpts are not eighteen correct answers.

The previously failing v2 split-count question now returns the `DELAY_V2.md` excerpt containing 1,611,046 training, 577,730 validation and 597,574 testing records. The selected excerpt cannot silently replace its April validation context with a February quote from another document. The eight-case source-coverage observation is local development evidence, not a general accuracy result.

Three failures remain prominent:

- The v1 rejection-reason question returns status/serving-limit excerpts but omits the expected probability-quality and alert-rate reason. Verbatim copying alone does not ensure the requested explanation is selected.
- With v2 selected, a request to ignore that selection and answer about v1 receives the v2 threshold excerpt instead of abstaining.
- With v1 selected, a request about v2 validation receives a v1 March evaluation excerpt instead of abstaining.

The two conflicting requests **did not retrieve another experiment's document**; the failure is returning an irrelevant selected-scope answer. This two-case challenge is not a comprehensive prompt-injection test. These failures prevent promotion. No prompt tuning, retries or replacement of the first results was performed.

## Boundaries and reproduction

Only two experiment identifiers are accepted; neither is inferred from free text. The existing retriever's explicit-document mode supplies up to eight passages from the chosen fixed source. Each returned identity/text/line range is compared with the loaded trusted index before generating options. Source spans must be 20–400 characters, deduplicated per passage, with at most 200 options. The local model emits integer IDs only. Free text, unknown IDs, booleans, duplicates, extra fields and incomplete model output are rejected. Provider/rejection failures return no selected excerpts and are not credited as abstentions.

Model and index identities are rechecked before returning. The evaluation also checks suite/code/model/index identity at the end, retains exact case outcomes and flushes progress to a new exclusive private journal. Public reports contain the fixed public questions, excerpts, locations, hashes and outcomes; they do not contain user sessions, vectors, raw flights or provider error messages. No database write, document/index rebuild, training, credential change or operational action is part of this workflow.

Single private research query:

```powershell
.\.venv\Scripts\python.exe -m rag.scoped_answers --experiment delay-v2 --question "How many eligible training validation and testing flights were used in the second delay experiment?" --output .local/evaluations/scoped-query-new.json
```

Full development evaluation, using a new filename:

```powershell
.\.venv\Scripts\python.exe -m rag.scoped_evaluation --output .local/evaluations/scoped-evaluation-new.json
```

Outputs must be new files under this checkout's `.local`. Existing reports/journals are retained. The evaluation CLI exits 2 for unavailable/rejected cases. Logical relevance failures remain visible in a completed report and must be reviewed; a zero exit is not an acceptance certificate. The individual-query CLI reports its mode/status, including unavailable selection, without implying success.

Twelve synthetic tests cover source separation, exact span construction, selection schema, fixed local transport, lock release, failure versus abstention, missing evidence, identity changes, suite labels, negative answers and private durable outputs. The actual model run is separate from these fixtures. The original retrieval and generation reports remain unchanged.

The next promotion requirement is explicit conflict handling plus relevance/completeness review on a separately authored challenge set, with a new versioned result. The current suite has now been inspected and is development evidence. The running Docker dashboard remains on its previously verified release. All 64 workspaces, account credentials, flight data, delay-v2 artifact and threshold remain unchanged. All 24 production requirements remain open.
