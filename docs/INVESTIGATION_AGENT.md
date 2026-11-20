# Bounded aviation research investigation agent

Current report-policy update: [agent report quality](AGENT_REPORT_QUALITY.md) adds explicit evidence requirements, scoped document retrieval, one repair call, verbatim findings and server-blocked acceptance of mechanical gaps. The original three-tool demo below remains historical baseline evidence; the current complete test count is 95.

The connected dashboard now includes an Investigation Desk. An actual local Qwen3 model selects tools through Ollama's native tool-calling interface, receives the tool observations and produces a cited research draft. The backend validates and executes each selection; a model cannot supply executable SQL, shell commands, file paths or destination URLs.

This is one bounded tool-calling agent implemented as a small custom runtime. It is not LangGraph, CrewAI, AutoGen, a multi-agent system or a deployed autonomous airline service.

## Available tools

| Tool | Implemented behavior | Scope |
|---|---|---|
| `flight_metrics` | Parameterized, read-only SQLite query for imported counts, cancellations, diversions, eligible completed flights and observed arrival-delay rate | One user-selected January–May 2025 month; historical US BTS records only |
| `knowledge_search` | Existing local embedding/TF-IDF retrieval with source passages and index identity | Six public project documents; no arbitrary upload or web browsing |
| `gate_simulation` | Actual mixed-integer gate optimizer with independent feasibility checking | Optional fixed five-flight synthetic example; never allocated to historical flights |

Aircraft gates, airline policies and UAE operational data do not exist in the BTS data. The simulation is explicitly separate. Its tool is not offered without the user's simulation opt-in, and server checks reject an attempted call even if a model invents it. Flight metrics accept only the selected month; the server rejects a different month. SQL text and additional arguments are forbidden. Unknown tools and duplicate selections are rejected before execution.

The SQL denominator is completed, non-diverted flights with observed arrival delay. Delayed means arrival delay of at least 15 minutes. Cancelled, diverted, missing-target and synthetic rows are excluded from that rate. Empty months return unavailable rather than an invented zero delay rate. The tool uses a read-only SQLite connection, query-only mode and a five-second progress-handler budget; no flight rows are changed.

## Execution, checkpoints and review

The runtime permits at most three planner calls and three tool executions, each tool at most once. Planner calls are bounded to 20 seconds, report generation to 30 seconds, and elapsed budget is checked between steps against a 120-second run budget. Individual blocking tool calls may finish after the budget boundary; this is not hard real-time cancellation. One investigation runs per API process; a busy run is rejected rather than queued. There is no distributed queue or worker lease.

SQLite migration 7 adds owner-scoped run records. Checkpoints are saved at creation, before and after each tool and at the terminal state. The trace records validated arguments, observed results, tool timing, model identity and bounded decision counts. It does not expose or store model chain-of-thought. Missing models, invalid decisions, failed tools, incomplete output and exhausted budgets remain visible as failures. Successful tools can remain useful when another tool fails; inspect each step rather than relying only on the report state.

The local database uses SQLite WAL journaling so a dashboard read snapshot does not block checkpoint writes. Startup refuses to claim readiness if WAL cannot be enabled. This is for local disk, not a network filesystem or distributed database; it does not establish backup/recovery qualification.

Owner-scoped UUID retry keys replay a completed or interrupted investigation without re-running tools. Reusing a key with different inputs returns conflict; an in-progress key is not re-executed. The browser advises checking saved history after a timeout because cancelling the client wait does not cancel backend work.

On service startup, unfinished running records become `interrupted`; the runtime never replays tools automatically. This assumes one API process using this local database. Concurrent API instances or production worker recovery require a different ownership/lease design.

Draft statements must cite executed tool evidence, copy an exact quotation and contain only numbers present in that quotation. Invalid statements are excluded with a visible rejection count. These mechanical checks cannot establish semantic entailment or completeness. No supported tool evidence means no generated report. Retrieved documents and tool observations are presented as untrusted data to the model, but prompt-injection resistance is not formally established.

The runtime also flags successful tool evidence that is not cited by any retained finding. Such drafts are labelled `coverage_incomplete` and the UI lists the omitted tool IDs. This detects missing tool coverage, not whether every part of a user's question was answered or whether cited interpretations are correct.

Completed drafts enter `awaiting_review`. Researchers can review their own reports; administrators can review all local reports. `reviewed` and `needs_changes` decisions bind to the displayed SHA-256 of the request, tool trace and accepted statements. The backend recomputes that hash before recording review. A changed or already-reviewed report cannot be reviewed through a stale request. Notes and review identity/time are preserved. To revise, start a new investigation; existing traces are not edited through the API.

**Research review never changes `operational_approval=false` and cannot trigger an airline action.** Local checkpoint/review records are not tamper-proof auditing. The local database contains research questions, findings and review notes in plaintext.

## Use and APIs

Start the existing local services and keep Ollama running with the models configured for the Evidence Studio. Sign in, expand Connected research data and open **From question to evidence**. The example button explicitly permits a separate synthetic simulation. Run, expand the trace, review the source evidence, record a research decision and export JSON.

- GET `/api/v1/research/agent-status`
- POST `/api/v1/research/agent-run` with objective, selected month, simulation opt-in and required UUID `Idempotency-Key`
- GET `/api/v1/research/agent-history` (latest ten accessible runs)
- POST `/api/v1/research/agent-review` with run ID, report hash, decision and note

Existing session, role and Origin/CSRF controls apply. New runs and reviews require admin/researcher access; viewers can read their own saved runs.

## Recorded evidence and limits

`reports/Investigation_Demo.json` records one curated actual-model run. Qwen3 selected all three tools; SQL returned 605,648 imported May flights, 597,574 eligible flights, 141,038 delays and a 23.6018% observed delay rate. The independent synthetic optimizer assigned five of five flights against a four-of-five greedy baseline. All three retained statements were manually checked against tool evidence. The document search executed, but the three-statement summary omitted the retrieved model limitations; this is a known completeness limitation, not a fully accepted report.

Browser checks in the signed-in administrator account confirmed the tool trace, saved history, report export and a `needs_changes` review explicitly labelled as development QA by the coding assistant. That note identifies the omitted limitations and approves no operational use. Responsive checks covered 390-pixel mobile and 1365-pixel desktop widths without mobile page overflow.

The full automated suite includes 70 Python and 13 Node tests. Agent checks cover SQL inclusion/denominators, actual solver execution on fixtures, native-tool selection contracts with mocked model responses, unknown tools, SQL argument injection, month scope, simulation permission, repeated calls, retry replay, persisted checkpoints during read snapshots, interruption, report hash/owner controls, rejected statements, deadline exhaustion, role enforcement and escaped UI output. Hosted tests do not require Ollama; the recorded actual-model example is separate evidence.

Future work includes larger evaluation sets, report completeness checks, framework integration if useful, more authorized aviation sources, durable background workers, production identity, monitoring and deployment/recovery qualification. There are no flight write, booking, messaging, maintenance approval or operational recovery tools.

Provider reference: [Ollama native tool calling](https://docs.ollama.com/capabilities/tool-calling).
