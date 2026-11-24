# Production delivery sequence

Target: a private aviation research portal using the historical public dataset and clearly synthetic operational scenarios. This is not an authorized airline control system. Continue locally while preparing for a future cloud choice; no paid resources, merge or deployment is authorized by this plan alone. Preserve all 64 workspaces, existing accounts, data, frozen model experiments and previous evidence.

The original production assessment retains 24 open requirements. Its dated entries must be reconciled with newer local evidence rather than interpreted as current missing-code counts. No requirement becomes production accepted just because a local test or PR passes.

| Order | Deliverable | Exit evidence required |
| --- | --- | --- |
| 1. Foundation | Request correlation, safe failure handling, configuration boundaries, identity/role controls, protected audit design and database migration/concurrency strategy | Executed positive/negative authorization and privacy tests; traceable failures; reviewed identity/database/audit architecture. Managed identity, MFA and protected logs remain later deployment dependencies. |
| 2. Data platform | Governed source manifests, scheduled incremental ingestion, quarantine/replay, time-safe joins and representative resource measurements | Measured batch reconciliation and recovery; source rights reviewed for the intended purpose; lineage linked to recorded results. Current five-month coverage is historical metadata evidence. |
| 3. Data science | Frozen experiments, chronological validation, baseline/error/cohort reporting, useful regression/forecast/anomaly objectives and model lifecycle | Reproducible evaluated artifacts, agreed decision criteria, monitoring and model rollback. Retain failed experiments; do not retune against an already-used test holdout. |
| 4. Product integration | One complete research incident-to-outcome journey before broadening workspaces | Reviewed user journey with real persisted research data, role boundaries, missing-evidence and dependency-failure behavior. Prototype workspace screens are not functional business services. |
| 5. Generative and agentic AI | Authorized corpus, evaluated grounding, scoped tools, isolated durable execution and governed review checkpoints | Human semantic evaluation, security/permission cases, restart/cancellation/failover tests and evidence-bound approvals. A structurally valid citation is not answer accuracy. |
| 6. Optimization | Explicit formulations, feasibility verification and reviewer-bound proposals | Representative authorized constraints, baseline comparison and scale/resource checks. Keep synthetic scenarios labelled; do not imply gate/crew operational authority. |
| 7. Release qualification | Cloud/private network, HTTPS, managed identity, external monitoring, protected off-site backups, recovery and rollout | Final-revision CI plus deployed journey, security, performance, accessibility and recovery evidence; independent review and responsible owners accept scope and remaining risks. |

## First foundation increment

The request-correlation change introduces server-generated API request IDs, allowlisted structured response-preparation events, generic correlated unhandled-error responses and validated proxy ID forwarding. See `REQUEST_CORRELATION.md` for execution and limitations. This is one local foundation increment, not completion of Phase 1 or protected audit.

The second local foundation increment is [configuration and secret-reference preflight](CONFIGURATION_PREFLIGHT.md): strict local settings, rejected unsupported security/secret declarations, safe diagnostic commands and startup admission checks. This validates supported environment settings; it does not implement a secret provider, managed identity or HTTPS.

Next foundation increment: define the private HTTPS/identity integration boundary and database migration/availability target, and agree the first release's users, workload and service objectives. The cloud/provider decision remains deferred under the user's local-first preference. Production profiles remain fail-closed until their required controls exist.

PRs remain reviewable and unmerged until explicitly authorized. PR #1 covers the single-batch trace; PR #2 adds the five-month coverage audit. Keep later increments separate and declare any stacked-branch dependency. After an eventual merge, verify the final main revision and its own checks before considering deployment. Do not deploy a branch merely because its development tests passed.
