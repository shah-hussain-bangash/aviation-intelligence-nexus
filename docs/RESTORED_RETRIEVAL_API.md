# Evidence retrieval through a restored-data API copy

The opt-in `--with-retrieval` mode of `infra.restored_data_api` connects a qualified full restore to normal proxy authentication, evidence-only search and owner-scoped saved history. It copies state into a fresh private case, uses disposable researcher/viewer passwords and stops only its own services. The original dashboard, users, database and source restore are not selected or changed.

```powershell
.\.venv\Scripts\python.exe -m infra.restored_data_api --recovery-report "<qualified full-restore case>/report.json" --report-sha256 <full-report-sha256> --expected-recovery-revision <full-verifier-revision> --with-retrieval
```

Use the same explicit source admission described in [Restored Data API](RESTORED_DATA_API.md). The qualified restore must include `knowledge/index.json`. This mode is separate from `--with-prediction`; combining them is rejected before reading the report. The default read-only and opt-in prediction modes retain their existing behavior.

## Model, corpus and HTTP checks

The existing `embeddinggemma:300m` model must be available through the fixed Ollama loopback endpoint at `127.0.0.1:11434`. There is no download, provider installation, remote model host or model-generation request. The copied index must pass hash/vector/source checks, match the exact chunks reconstructed from the six allowlisted public documents, and name the installed embedding digest. A self-consistent index containing forged passage text is refused.

Preparation computes direct evidence-only results on that copy for a local-session-expiry question and an unrelated photosynthesis question. The former must retrieve the local-identity source; the latter must abstain. These are declared engineering probes of public project documents, not airline operational scenarios or an accuracy benchmark.

The rehearsal checks anonymous denial for knowledge history/query, normal researcher login, empty owner history, two authenticated POSTs with `generate: false`, parity with the direct copied-index results, no generated claims and preserved research-only scope. It restarts only the owned API and verifies that the same session can read the two saved results afterward. A separate viewer must see no researcher/original-owner history and must receive 403 on query mutation. Existing CSRF, origin, logout and retained dataset checks also run.

After shutdown, SQLite checks preserve all original owner rows and require exactly two new knowledge rows matching the saved IDs, payloads and timestamps. Original business tables, users, audit prefix and migrations retain the existing preservation checks; expected probe accounts/sign-ins/sign-outs are counted separately. Artifact bytes, copied index identity, provider digest and original qualified source hashes must still match. Changing a saved query payload fails the consistency check.

## Validation and limits

Focused check: `python -m unittest tests.test_restored_retrieval_api -v`. The normal-authentication/proxy integration test injects synthetic embedding functions only into disposable test workers/API processes; it does not bypass authentication or contact an Ollama daemon. Other tests cover invalid combined modes, missing index, forged chunks and changed provider identity. A native run against the real local provider is separate evidence. Run `npm test` for regression checks.

The report records index/model identity, probe questions, evidence counts, saved run IDs, restart checks and state preservation. It does not establish semantic answer quality, protected auditing, embedding-weight recovery, an original-account browser journey, cloud deployment or production readiness. `generate: false` is mandatory in the fixed probes; this is the retrieval/history portion of RAG, not a generated-answer evaluation. No model is fitted or changed, and all existing synthetic operational labels and production requirements remain open.
