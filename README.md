# Aviation Intelligence Nexus

An independent aviation decision-support portfolio project combining a comprehensive dashboard prototype with an explicit implementation and acceptance roadmap.

**Current status: frontend prototype. Real backend services, trained models, generative AI, agent execution, optimization, authentication and production deployment are not implemented.**

![Aviation dashboard prototype](docs/images/dashboard.jpg)

## Run locally

Requirements: Node.js 24+ and Git. The current frontend has no third-party runtime dependencies.

```sh
npm run check
npm run dev
```

Open **http://127.0.0.1:8080**. Stop the local server with Ctrl+C.

You can also open `apps/web/index.html` directly. A local server gives browser storage a consistent origin.

## Included today

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

All shipped operational records are synthetic. Large datasets, credentials, personal documents and local databases are excluded from Git. Source registrations do not grant data rights. A local review does not enforce authentication or authorize an airline operation.

AIN is not affiliated with Emirates, Etihad or any airline. It does not provide dispatch, air-traffic, maintenance-release or passenger-communication authority. Use a production description only after implementation and verified deployment, security, monitoring and recovery evidence.
