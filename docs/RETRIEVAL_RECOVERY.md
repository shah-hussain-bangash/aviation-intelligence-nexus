# Copied-index retrieval recovery parity

`infra.retrieval_recovery` checks an existing pinned project-evidence index before and after backup/restore in a fresh synthetic schema-8 state. It uses the already installed loopback Ollama embedding model. It never rebuilds the dense index, downloads model weights, generates an answer, opens the original snapshot's database or changes the live knowledge service.

```powershell
.\.venv\Scripts\python.exe -m infra.retrieval_recovery --snapshot "<reviewed local snapshot directory>" --manifest-sha256 "<64-character manifest SHA-256>"
```

## Admission and source evidence

The caller supplies the exact manifest digest. Bounded ordinary local files, unique allowlisted inventory entries, schema 7/8 snapshot metadata and a UUID are required. Only `knowledge/index.json` and the manifest are opened from the source snapshot. The source flight database and model pair are not required or read.

The index file must match its inventory size/hash. Strict JSON parsing rejects duplicate keys. Its embedding model/digest, envelope hash, approved source order/hashes and finite 768-dimensional vectors must pass validation. Every stored chunk, heading, quote, line range and ID must exactly match chunks reconstructed from the six current allowlisted project documents. A self-consistent altered payload is insufficient. This validates local consistency with project files, not publisher authentication or source rights for an airline manual.

## Isolated recovery flow

1. Copy the admitted index into a new private case. Launch a fresh child process with that case as state, workers/monitor off and the embedding client fixed to `127.0.0.1`. The ordinary local client refuses proxy forwarding and redirects.
2. Require the installed embedding model digest to match the recorded index. Create one synthetic account, session and flight row; no original accounts or flight records are copied.
3. Query two fixed scopes using the existing `Knowledge.query` path and `generate=False`: historical delay-model limitations and synthetic gate-assignment cost. Both must return scoped evidence. An unrelated photosynthesis question must abstain. No generated claims are accepted.
4. Back up the synthetic state and copied index, restore into a new directory, then use a fresh retrieval cache and new local embedding requests for the same questions. Entire result objects, including evidence IDs/text/ranges/source hashes/links and rounded scores, must match exactly. Ordinary cache reconstruction is not a dense-index rebuild.
5. Observe the embedding digest again, check index byte parity, source-state preservation, restored-session revocation and offline row/receipt/event consistency. Recheck the original source manifest/index pins after the child exits.

The private report is `.local/retrieval-recovery/<case>/report.json`. It includes harness/verifier/helper fingerprints, index/source manifest pins, provider digest, evidence-only results and restore/offline receipts. Failure details from the child are withheld behind a generic diagnostic. Raw indexes, reports, fixtures, snapshots, credentials and local logs stay outside Git.

## Verification and limitations

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_retrieval_recovery -v
npm.cmd test
```

Tests use synthetic dense vectors and an explicitly mocked embedding provider; they do not require Ollama. They reject changed pins, forged self-consistent chunks, malformed inventory/vectors and a changed embedding identity. A real child-process fixture exercises retrieval, restore, scoped evidence, abstention, session/audit evidence and disabled generation. Separate native operator evidence is needed for actual local embeddings.

Ollama must already be available with the original embedding digest. Missing/changed models or retrieval differences fail the run; there is no fake-vector fallback. Tags/digests are observed through the existing local service, not independently authenticated weight measurements. The CLI has a child time budget and operates on owned private copies; it is not a hostile-input isolation boundary.

Two scoped queries and one abstention demonstrate local recovery parity only. They do not establish semantic relevance across a benchmark, answer entailment, Arabic performance or generation quality. Embedding weights, the generator, the full historical database, browser sessions, independent/off-host recovery and production availability are not recovered or qualified by this increment.
