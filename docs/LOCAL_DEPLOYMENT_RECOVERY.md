# Local deployment and recovery

This milestone adds a tested Docker Desktop release and restoration of the workstation's research state. It is a local deployment foundation, not production qualification. The 64 workspaces remain available; only the documented research services have real backend implementations.

## Build and start

Requirements: Docker Desktop with Linux containers, the project Python environment, and existing host Ollama with `embeddinggemma:300m` and `qwen3:8b`. Run from the repository root in PowerShell:

```powershell
$env:AIN_RELEASE_REVISION = git rev-parse HEAD
docker compose build api web
docker compose up -d --wait --wait-timeout 90 api web
python -m infra.verify_deployment --project ain-local-release --port 8090
```

Open http://localhost:8090. A fresh volume creates an empty database; it does not include this workstation's data, model or accounts. Import/train/index or restore trusted state before using those capabilities. Existing native development remains at port 8080. The release uses a separate cookie namespace so the two instances do not replace each other's login cookie. Credentials are preserved by restoration, but restored sessions are revoked: sign in again.

The API and web images pin base-image digests, run as user 10001 with read-only root filesystems, drop capabilities and prohibit privilege escalation. Only the dashboard's loopback port is published; the API has no published host port. The API has a bounded 256 MiB temporary filesystem; full-dataset summary aggregation was retested after the initial 64 MiB limit proved insufficient. These checks are not a vulnerability assessment or network egress restriction. Docker's standard bridge permits access to host Ollama through `host.docker.internal`; host configuration and model weights are not included in the images or backup. This AI route was tested on Windows Docker Desktop. Linux CI tests core containers without host AI or real data.

`/__ain/health` is frontend liveness. `/__ain/ready` checks database-backed API readiness and returns 503 during a backend outage. It does not exercise every model, tool or user journey. The authenticated **Know what is running** card separately reports runtime, artifact identity checks, model availability and any recorded restore receipt for that instance.

## Take a trusted local snapshot

Use a new destination every time. Do not replace existing backups:

```powershell
python -m infra.recovery backup --source .local --destination .local/recovery/backups/my-new-snapshot
python -m infra.recovery verify --source .local/recovery/backups/my-new-snapshot
python -m infra.recovery restore --source .local/recovery/backups/my-new-snapshot --destination .local/recovery/restores/my-new-drill
```

SQLite's online backup API captures committed database state. The manifest records hashes, sizes, schema and row counts. Active v2 model/report and the knowledge index are copied and checked. Avoid replacing the model/index during snapshot creation; this is not an atomic cross-service backup. Raw downloads, training datasets, the retired v1 artifact and Ollama weights are excluded. Keep matching source and dependencies for restoration.

Backups contain account password hashes and research history. They are private, locally stored, unencrypted and unsigned. Checksums detect corruption, not malicious replacement. Restore only your own trusted backups; model serialization is not safe for untrusted input. Protected storage, encryption, retention automation and off-site recovery are not implemented. Neither backups nor state belongs in Git or an image.

## Restore into a fresh Docker volume

For the first restore only, before starting the services, mount the trusted snapshot read-only and restore into the new volume's `active` directory:

```powershell
$snapshot = (Resolve-Path .local/recovery/backups/my-new-snapshot).Path
docker compose run --rm --no-deps --volume "${snapshot}:/restore:ro" api python -m infra.recovery restore --source /restore --destination /app/.local/active
docker compose up -d --wait --wait-timeout 90 api web
docker compose exec -T api python -m infra.validate_restored_state --with-ai
python -m infra.verify_deployment --project ain-local-release --port 8090
```

The restore refuses an existing destination. If services already initialized `active`, use a separately named AIN Compose project and an unused loopback port for a fresh drill; do not remove or overwrite the existing volume. Stop only the explicitly named project when appropriate. No automatic rollback, volume deletion or live replacement is provided.

The operator smoke test exercises the restored model, scoped retrieval and a known three-tool agent scenario. It records an operator research run, not authenticated user acceptance or operational approval. Interrupted agent work is marked interrupted rather than replayed on restoration.

## Measured local evidence

The snapshot restored **2,835,101 flights** with database integrity, checksums and expected row counts verified. Account hashes were preserved and restored sessions revoked. Native file restoration/validation took 14,290.33 ms; Docker-volume restoration/validation took 74,095.3 ms. These timings exclude provisioning, model service startup and human acceptance; neither is a full-system recovery-time objective.

The restored historical AA/JFK/LAX scenario for 2025-05-15 at 09:00 returned exactly the native research probability, 0.14414301173592028. Scoped local retrieval and the known agent regression completed with all three tools and passed mechanical coverage. An initial differently worded probe failed closed on invalid model-generated tool arguments. This is evidence of the guard, not proof of general agent reliability; human semantic review remains required.

All 16 container smoke/isolation checks passed. A controlled API stop/start returned readiness 503 while frontend liveness remained available; services recovered healthy with all flight rows preserved. Re-run that disruptive drill only when no user workflow is active:

```powershell
python -m infra.outage_drill
```

That command targets only `ain-local-release` on 8090. It is not an infrastructure disaster simulation. The receipt is an ordinary local file, not a protected audit or continuous recovery guarantee. See [sanitized evidence](reports/Local_Deployment_Recovery.json).

## Remaining production work

Managed HTTPS/TLS, identity/MFA, protected auditing, monitored alerts, encrypted off-site backup storage, retention, restore drills on an independent environment, durable workers, high availability, resource/load testing, vulnerability review, deployment rollback and cloud acceptance remain incomplete. Native Ollama is an external local dependency. No airline operational feed, decision authority or UAE model approval is implied.

The suite contains 108 automated tests (90 Python, 18 Node). GitHub additionally defines a fresh Linux container build, health/isolation verification and restart smoke check. Hosted results must be checked for the actual published commit; CI fixtures do not repeat the workstation's million-row restoration or AI run.
