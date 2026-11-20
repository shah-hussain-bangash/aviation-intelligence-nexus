# Project status

## Delivered

Agent quality milestone: explicit tool-evidence requirements, approved document scoping, one bounded repair call and verified source-extract findings are implemented. The server recomputes coverage before accepting research review and blocks mechanically incomplete reports. All seven curated development cases now pass their defined checks; manual inspection still found a broad-corpus relevance gap, so this is not a general accuracy or full task-completeness claim. Current suite: 95 automated tests. See `AGENT_REPORT_QUALITY.md`.

Agent milestone: a local Qwen3 tool-calling investigation runtime selects and executes up to three restricted tools: historical BTS SQL metrics, project-document retrieval and opt-in synthetic gate optimization. Execution checkpoints, scoped retry replay, interruption records, cited drafts, saved/exportable reports and hash-bound research review are implemented. A real three-tool run was observed, and browser QA recorded `needs_changes` because its summary omitted retrieved model limitations. This is a bounded single-agent research workflow, not an operational or multi-agent platform. The original milestone passed 83 tests; the quality update above supersedes that count. See `INVESTIGATION_AGENT.md`.

Local RAG milestone: six public project documents are ingested into 31 passages with 768-dimensional embeddings and source-line provenance. Hybrid retrieval, optional actual Ollama/Qwen3 generation, citation/quotation/number checks, abstention, owner-scoped history and JSON export are implemented. Eight curated retrieval/abstention checks passed and two questions produced locally generated answers inspected against their sources. The complete suite now passes 71 automated tests locally. This is bounded project-research Q&A, not airline-manual coverage, production qualification or an agent runtime. See `KNOWLEDGE_STUDIO.md`.

Operations Research milestone: Gate Allocation Lab computes synthetic proposals with a mixed-integer solver, independently checks conflicts and aircraft compatibility, compares a greedy baseline and persists owner-scoped results. The exact five-flight sample assigns 5/5 versus the greedy baseline's 4/5 with the default settings. All 62 current automated tests pass locally. This is a bounded research demonstration, not real airline allocation or production readiness. See `GATE_OPTIMIZATION.md`.

Sign-in UX update: the app now opens on a dedicated sign-in screen and reveals its existing 64 workspaces after a verified session. Sign-out or expiry returns to sign-in. This display gate does not replace backend authorization.

Identity milestone: local account creation, Argon2id hashing, expiring/revocable sessions, Origin/CSRF controls and server-enforced admin/researcher/viewer permissions are implemented. History is scoped to its authenticated owner, with legacy anonymous rows visible to administrators. First administrator creation and browser sign-in were verified; managed production identity, MFA, HTTPS deployment and protected auditing remain incomplete. See `LOCAL_IDENTITY.md`.

Developer workflow milestone: `npm run dev:all` starts or safely reuses both local services, and `npm test` runs all 41 automated tests plus source checks. Dependency consistency passed locally. GitHub workflow now defines independent Linux/Windows Python checks and Linux Node checks; hosted execution must be verified against the published commit rather than inferred from local results. See `DEVELOPMENT.md`.

Persistent research history milestone: successful scenario calculations now store their inputs, output, model/artifact identity and UTC save time. Latest-ten review and JSON export are available in the dashboard. Retry keys prevent duplicate records for the same request, and conflicting reuse returns 409. Thirty-two Python and six Node tests passed, including unavailable-history failure behavior. Actor identity remains anonymous local; this is not tamper-proof or production auditing. See `RESEARCH_HISTORY.md`.

Research inference milestone: a bounded historical-scenario form now calls the real v2 model. Unsupported vocabulary, dates outside January–May 2025, invalid fields and failed artifact/research checks prevent scoring. Twenty-five Python and five Node tests passed, including an actual dashboard-server routing regression. This changes only local research demonstration capability; operational model serving and production qualification remain disabled. See `RESEARCH_PREDICTION.md`.

Dashboard integration milestone: the separate connected research panel now reads actual BTS database aggregates and verified v2 report metrics through a fixed local API proxy. Twenty Python tests and two Node tests passed. Browser checks covered desktop/mobile rendering and backend outage/recovery. Prediction serving remains disabled. Other workspaces and the original production audit retain their prototype/baseline scope. See `CONNECTED_DASHBOARD.md`.

Second modelling milestone: five-month database now has 2,835,101 flights. Categorical gradient boosting trained on January–March and selected on April passed prespecified research comparisons on May: ROC-AUC 0.6506, log loss 0.5261 versus prior 0.5511. Operational serving remains unapproved; false alerts and calibration drift remain concerns. Full evidence: `reports/Delay_v2.json`, with protocol and freeze receipts preserved locally. See `DELAY_V2.md`.

Modelling milestone: a one-hot logistic model was trained on January, selected on February and evaluated on March once. Test ROC-AUC was 0.5604; log loss 0.5485 was worse than constant-prior baseline 0.4949. It is a research artifact rejected for serving, not a usable operational predictor. Serialization integrity and carrier/calibration diagnostics are recorded in `reports/Delay_Baseline_v1.json`. See `DELAY_BASELINE.md`.

Chronological dataset milestone: February and March 2025 were added, bringing the local database to 1,645,503 flights. A reproducible dataset builder prepares January training, February validation and March testing files, with feature allowlisting, exclusion accounting and output hashes. Eleven API, ingestion and dataset tests passed. See `MODEL_DATASET.md` for the fixed experiment contract and limitations.

Local data milestone: January 2025 BTS archive imported with 539,747 records, 14 carriers, archive hash/source provenance and atomic validation. Repeat import was verified to skip the existing archive without duplicating records. Eight API/ingestion tests passed. See `DATA_INGESTION.md` and `reports/BTS_2025_01_Import.json`. This does not complete the broader production data requirement.

The current frontend preserves 64 workspaces, 256 specified functions, 72 acceptance requirements and four connected local case walkthroughs. Previous checks covered 320 workspace views and local interaction flows. The completion report adds details, filters and exports for all 24 production gaps.

## Not yet delivered

Current outstanding work includes broader authorized aviation document ingestion, report completeness and agent evaluation, durable worker orchestration, operational-scale optimization and validation, managed identity, cloud deployment, monitoring and measured backup restoration. The implemented local research capabilities above do not complete these production requirements.

The production audit records **20 areas not implemented, 3 partially evidenced and 1 unverified**. No production requirement is independently verified complete and no production service is connected.

The original production audit predates the local inference, solver, authorization, RAG and agent milestones above. Its counts describe that baseline and must not be presented as a current acceptance assessment. No cloud monitoring or measured production backup restoration is claimed.

See `reports/AIN_Completion_Report.json` for the full baseline and `ROADMAP.md` for implementation order. Update this document with verified evidence as capabilities are built; local review labels cannot change implementation facts.
