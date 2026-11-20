# Agent report quality and evidence coverage

The investigation agent now distinguishes explicit evidence requirements, source-extract fidelity and human acceptance. Its findings use verified source wording. One bounded repair attempt can add omitted evidence. Reports with unresolved mechanical gaps cannot be marked reviewed, even if a browser or cached result claims they passed.

This strengthens the existing local research workflow. It does not establish production readiness, general answer accuracy or complete natural-language understanding.

## What is checked

- The user can require historical metrics, document evidence and an explicitly permitted synthetic simulation. A requested simulation without permission is rejected by the request contract.
- The model still selects tools. If it finishes early, the bounded planner can receive a reminder about missing required tools; it never gains extra tools or execution budget.
- Required tools must have executed, executed steps must have completed, and returned evidence must be available. Every successful evidence source needs a retained finding.
- Selected quotations must exist exactly in executed tool evidence. Published finding text is set to that quotation; the model's rewritten interpretation is discarded. Metadata lines, headings and empty/separator-only material cannot satisfy finding coverage.
- Stored retained findings are rechecked, including quotation, number and exact-wording integrity. A cached `quality.passed` flag cannot bypass the server check.
- The existing report hash still binds request, tool trace and retained findings. Missing coverage, mismatched document scope, invalid findings or an altered report block a `reviewed` decision. `needs_changes` remains available for incomplete drafts.

The quality panel names gaps, reports source coverage and shows repair status. Passing means these explicit evidence checks passed. It does not mean that every part of the objective was answered or that an extract is relevant in context; those fields are explicitly false in the machine-readable quality record. A human can still request changes after a coverage pass.

## Bounded repair

The first summary selects at most three findings. If successful tool evidence is omitted, one additional local model call receives only those missing sources and can select at most three more findings. Both calls stay inside the existing elapsed-budget checks, with at most six retained extracts. Repair progress is checkpointed. A failed, malformed, unsupported or budget-skipped repair leaves the gate blocked; it is not retried indefinitely and cannot mark itself accepted.

The three-tool and three-planner limits remain unchanged. There are at most two summary calls. This is still the custom single-agent runtime, now identified as `bounded-ollama-tools-v2`; it is not a multi-agent or LangGraph implementation.

## Document scope

The UI can select one of the six approved public project documents. If the objective names exactly one approved document path, automatic mode scopes retrieval to that document. Multiple mentioned documents preserve corpus-wide retrieval for comparison; no arbitrary file or URL is opened.

Broad retrieval still returns at most three ranked passages. For an explicitly scoped small document, once a matching passage qualifies, retrieval includes up to eight passages from that same document to retain context. This fixed corpus is small; the behavior is not an unbounded document-loading mechanism. Existing index hashes and source validation remain in force; changing scope does not require re-embedding the corpus.

This change addressed a measured failure: the model-limitations question retrieved the v2 document alongside v1/data-preparation documents, then selected v1 material. Scoping the named v2 document and retaining its context corrected the specific case. The example button now visibly selects the second delay experiment as its document scope.

## Evaluation evidence

Run the actual local-model development cases with:

```powershell
.\.venv\Scripts\python.exe -m agents.evaluate
# A focused rerun is also available:
.\.venv\Scripts\python.exe -m agents.evaluate --case v2_limitations
```

`agents/evaluation_cases.json` defines seven versioned engineering cases. The report records its contract hash, model digest, retained extracts, repair outcome, observed tools, retry replay and individual check results.

| Recorded run | Defined checks passing | Meaning |
|---|---|---|
| `reports/Agent_Quality_Baseline.json` | 6/7 cases | The v2-document relevance case failed despite tool coverage |
| `reports/Agent_Quality_Evaluation.json` | 7/7 cases | Current deterministic checks passed after source-scoping and extract handling changes |

These cases were used during development; they are not a held-out airline benchmark and 7/7 is not a general accuracy percentage. Two cases evaluate restricted tool behavior under an injection attempt or missing simulation permission, not answer quality. The unknown-CEO case correctly returned no accepted answer. The integrated case used its one repair attempt to cover omitted document evidence.

Manual inspection also found an unresolved semantic limitation: in broad-corpus mode, the integrated case's document extract described the feature allowlist rather than the requested model limitations. Its mechanical source coverage passed, but human acceptance of that answer is not established. This is explicitly recorded in the evaluation report. The scoped v2 case did select operational-approval and generalization-limit extracts. Broader relevance and natural-language completeness evaluation remain future work.

## Compatibility and tests

Historical run content and decisions are not rewritten. History responses derive current quality checks for old reports. Previously incomplete awaiting-review reports can no longer be accepted through the new review endpoint. Old reviewed decisions remain historical records, not retroactive certification. Retry keys remain compatible when new optional requirements are empty and document scope is absent; adding an actual requirement or scope changes the input contract and cannot reuse that key.

The automated suite contains 81 Python and 14 Node tests. New checks cover bounded repair, failed repair, required-tool omissions, unavailable evidence, cached-quality tampering, legacy history/retry behavior, verbatim findings, metadata rejection, document scope, blocked API acceptance and escaped UI warnings. Actual Ollama execution is recorded separately; hosted tests use isolated databases and mocked model responses.

The UI also keeps service-status requests separate from editing state, so loading an example before readiness completes does not leave the Run button stuck. Saved investigations include UTC timestamps and short run IDs to distinguish similar objectives.

Browser checks on 20 November 2026 used the existing signed-in administrator account. They verified that an older 2/3-source report disables acceptance, the scoped example shows 3/3 coverage with a v2 model-limitations extract, the review control remains separate from the gate, and exported JSON retains quality metadata. Loading the example before readiness finished no longer blocked Run. Desktop (1365 pixels) and mobile (390 pixels) views were checked; the mobile page had no horizontal overflow. These are UI observations, not production acceptance tests.

Existing local account credentials, the 64 workspaces and the no-operational-write boundary are preserved. Managed deployment, monitoring, durable workers, protected auditing and recovery qualification remain incomplete.
