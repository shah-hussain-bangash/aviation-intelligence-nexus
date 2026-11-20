# Aviation Intelligence Nexus

An independent aviation decision-support portfolio project combining a comprehensive dashboard prototype with an explicit implementation and acceptance roadmap.

**Current status: local research prototype with an authenticated historical-data/model panel, role-checked scenario inference, SQLite history, BTS ingestion, two measured model experiments, a synthetic gate-allocation optimizer, local document RAG and a bounded tool-calling investigation agent. The second model passed prespecified research checks; neither model is approved for operational airline serving. A local Docker release and measured restoration are implemented; managed production identity and cloud deployment remain incomplete.**

![Aviation dashboard prototype](docs/images/dashboard.jpg)

## Run locally

Requirements: Node.js 24+ and Git. The current frontend has no third-party runtime dependencies.

```sh
npm run check
npm run dev
```

Open **http://127.0.0.1:8080**. Stop the local server with Ctrl+C.

For the connected API and dashboard together, use `npm run dev:all` after installing the project Python environment. `npm test` runs the complete local test suite. See [daily development](docs/DEVELOPMENT.md) for setup and GitHub checks.

You can also open `apps/web/index.html` directly. A local server gives browser storage a consistent origin.

## Included today

- Local Python API with liveness/readiness checks, persistent SQLite schema and truthful record counts. See [backend setup](docs/BACKEND_SETUP.md).
- Three-month BTS import (1,645,503 local records) and chronological training/validation/test dataset preparation. See [model dataset](docs/MODEL_DATASET.md).
- Trained and evaluated logistic delay baseline, artifact integrity and measured suitability review. See [model results](docs/DELAY_BASELINE.md).
- Five-month database (2,835,101 local records) and a prespecified gradient-boosting experiment trained on 1,611,046 flights. See [second experiment](docs/DELAY_V2.md).
- Connected historical research panel with actual database counts, same-period model comparison and verified backend failure/recovery states. See [dashboard setup](docs/CONNECTED_DASHBOARD.md).
- Local historical-scenario form with actual v2 model inference, strict scope checks and research-only output. See [research prediction](docs/RESEARCH_PREDICTION.md).
- Persistent local research history with model/input provenance, retry deduplication, saved-result review and JSON export. See [research history](docs/RESEARCH_HISTORY.md).
- Local password sign-in, expiring sessions and server-enforced admin/researcher/viewer roles. See [account setup and limits](docs/LOCAL_IDENTITY.md).
- Gate Allocation Lab with an actual mixed-integer solver, independent conflict checking, greedy comparison, saved proposals and JSON export. Synthetic research scenarios only. See [optimization evidence](docs/GATE_OPTIMIZATION.md).
- Local aviation research Q&A with neural embeddings, hybrid retrieval, actual Ollama generation, checked citation/quotation references and saved/exportable results across six public project documents. See [evidence studio setup and limits](docs/KNOWLEDGE_STUDIO.md).
- Local investigation agent with actual model-selected tools, read-only SQL metrics, document retrieval, optional synthetic optimization, persisted execution checkpoints and report-bound research review. See [agent evidence and limits](docs/INVESTIGATION_AGENT.md).
- Agent report quality checks with explicit evidence requirements, document scope, one bounded repair, verified source extracts and server-blocked acceptance of mechanically incomplete reports. See [measured checks and remaining semantic limits](docs/AGENT_REPORT_QUALITY.md).

- Local Docker release with loopback-only dashboard, non-root/read-only containers, trusted snapshot verification, measured restoration and controlled API outage/restart checks. See [deployment and recovery](docs/LOCAL_DEPLOYMENT_RECOVERY.md).

- All 64 original aviation workspaces across eight departments.
- 256 function specifications and 72 acceptance requirements.
- Four connected **browser-local** case journeys with evidence notes, human review, revision history and export.
- Local record tools, fixture checks and manually advanced job rehearsals.
- An evidence-based completion report covering 24 outstanding production areas.
- Responsive UI, editable source and documented frontend checks.

The historic 320 view checks are UI evidence, not production acceptance or model-performance results. See [the completion report](docs/reports/AIN_Completion_Report.html) and [current status](docs/PROJECT_STATUS.md).

## Source layout

```text
apps/web/              Editable frontend and local completion report
scripts/               Local server, validation and sync-plan tools
docs/reports/          Completion audit, specification and check evidence
docs/images/           Sanitized prototype screenshots
docs/ROADMAP.md        Implementation priorities
docs/GITHUB_SYNC.md    Daily review and synchronization policy
.github/workflows/     Source validation on push and pull request
.vscode/               Editor tasks
```

The existing browser application is currently a single shared script. Refactor it into tested components as real services are introduced, preserving all workspaces and existing local interactions.

## Daily work and GitHub

Open this repository folder in Visual Studio Code and save your work normally. The requested Codex automation reviews this checkout daily at **20:00 Asia/Dubai**, validates eligible changes, creates a meaningful commit and pushes to this repository when it is safe to do so. It stops for conflicts, failed checks, uncertain sensitive content or changes outside the approved scope. It does not force-push or discard work.

`npm run sync:plan` shows local eligibility only; it never commits or pushes. GitHub credentials stay in the operating system's credential manager, not this repository. See [sync policy](docs/GITHUB_SYNC.md).

## First implementation milestone

Authorized historical flight data -> persistent database -> evaluated delay baseline -> versioned API -> dashboard. Build real identity and permission controls alongside the service foundation. Expand to grounded retrieval, governed agents and verified recovery optimization after the core pipeline works.

## Data and operational boundaries

The dashboard's bundled operational records are synthetic. The separate local database now contains an official BTS January 2025 import; see [data ingestion](docs/DATA_INGESTION.md). Large datasets, credentials, personal documents and local databases are excluded from Git. Source registrations do not grant data rights. A local review does not enforce authentication or authorize an airline operation.

AIN is not affiliated with Emirates, Etihad or any airline. It does not provide dispatch, air-traffic, maintenance-release or passenger-communication authority. Use a production description only after implementation and verified deployment, security, monitoring and recovery evidence.
