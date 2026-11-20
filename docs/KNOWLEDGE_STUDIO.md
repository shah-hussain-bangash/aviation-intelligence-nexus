# Aviation research evidence studio

The connected dashboard now offers working local retrieval-augmented generation (RAG): ingest approved project documents, create neural embeddings, retrieve passages, optionally generate a cited answer through Ollama, validate citation references and quotations, save the result and review/export it. This is research Q&A about the project, not an airline operations manual or an agent runtime.

## Local setup

Install Ollama from its official distribution and keep its loopback service running. The workstation already had `embeddinggemma:300m` and `qwen3:8b`, so this milestone required no model download. For a fresh installation:

```powershell
ollama pull embeddinggemma:300m
ollama pull qwen3:8b
.\.venv\Scripts\python.exe -m rag.index
npm.cmd run dev:all
```

The explicit build command indexes exactly six allowlisted public Markdown documents: the two delay experiments, ingestion, chronological dataset, local identity and gate optimization. It never scans user folders or follows arbitrary URLs. No confidential airline manuals, CVs, uploaded PDFs or flight database rows are indexed. Extending document formats and authorized corpora is future work.

The local index contains 31 passages with relative paths, headings, exact line ranges, source hashes, a Git revision and 768-dimensional dense vectors. It is atomically written under `.local/knowledge/index.json` and excluded from Git. Source changes, a changed embedding-model digest, malformed vectors or an invalid index checksum prevent searching until the index is rebuilt. The checksum detects accidental modification; it is not a signed trust boundary or tamper-proof storage.

## Retrieval and generation

Retrieval combines normalized dense cosine similarity (65%) and TF-IDF similarity (35%), returning at most three passages. Conservative lexical and semantic thresholds permit abstention. Scores are ranking values, not confidence probabilities. These settings were exercised during development; the small demonstration is not a held-out relevance benchmark.

Generation is optional and off by default. The server uses fixed local Ollama endpoints, an embedding-model digest check, Qwen3 structured output, temperature zero, an 8192-token context setting, at most three claims and a bounded generation request. It passes no tools, credentials or operational write capability to the model. Questions and passages are explicitly treated as untrusted data in the prompt. This instruction is a mitigation, not proof of prompt-injection immunity.

Returned claims must reference a retrieved passage and copy an exact supporting quotation. Every number in a claim must also occur in its quotation. Invalid or unavailable generation produces evidence-only output with an explicit message. Source IDs, quoted text and numbers are mechanically checked; those checks do not establish full semantic entailment, completeness or factual correctness. A human must review generated interpretations. The model can still omit facts or select an irrelevant but real quotation.

The generation lock prevents concurrent chat calls within one API process. It is not a durable queue or a distributed quota. Provider timeouts, user cancellation and resource contention remain possible. A browser timeout can occur after a server request starts; the UI instructs users to inspect saved queries before retrying. Queries do not currently have idempotency keys.

## Access and history

Admin/researcher access is required for new searches or generation; viewers can review their own saved results. Existing Origin/CSRF/session controls apply to the new routes:

- GET `/api/v1/research/knowledge-status`
- POST `/api/v1/research/knowledge-query` with `question` and optional `generate`
- GET `/api/v1/research/knowledge-history`

SQLite migration 6 adds a separate owner-scoped result table. Successful responses require persistence. Administrators can review all local queries; other users see their own latest ten. Saved results include the question, passages, source and index hashes, model identity when used, generated claims, actor and UTC time. This is local plaintext research history, not protected production auditing. The UI renders evidence as escaped text, limits source links to versioned files in this public repository and supports JSON export.

## Measured evidence

`python -m rag.evaluate` runs eight curated engineering questions and writes `docs/reports/Knowledge_Demo.json`. In the recorded local run, all eight retrieval/abstention checks passed: six expected documents appeared in the top three and both unrelated questions abstained. Two requested, answerable questions produced actual local Qwen3 answers. Their five statements were manually compared with the retrieved source passages: May ROC-AUC 0.6506 and 241,732 false alerts; gate coverage priority, wide/narrow compatibility and buffer semantics matched the documents. These observations do not justify a general accuracy percentage.

Automated checks use mocked local-model responses and temporary databases, so CI requires no model download, GPU or user account. They cover line provenance, citation/number rejection, index/source/model changes, unavailable generation, missing index, permissions, persistence/restart and HTML escaping. Actual local model execution is separately recorded by the curated demo.

Browser verification on 20 November 2026 confirmed a generated answer and abstention in the normal signed-in administrator account, saved-result review, expandable source evidence, versioned source links and JSON export. The layout was checked at 390-pixel mobile and 1365-pixel desktop widths; the mobile page had no horizontal overflow. An additional temporary account/database was used for isolated UI checks and its services were stopped afterward. Existing credentials were unchanged.

## Remaining work

Larger authorized aviation corpora, PDF/OCR parsing, a scalable vector database, document-level permissions, formal retrieval/faithfulness evaluation, adversarial testing, managed model serving, deployment, monitoring and recovery qualification remain incomplete. No agents or airline actions are executed, and this system is not production-qualified.

Provider references: [Ollama chat](https://docs.ollama.com/api/chat), [Ollama embeddings](https://docs.ollama.com/api/embed).
