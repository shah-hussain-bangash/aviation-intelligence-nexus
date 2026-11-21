# Isolated application release rollback

AIN includes an operator-only rollback controller for a separate restored local deployment. It records the API/web image IDs, source revision, schema version and selected state-contract fingerprints. A drill switches the isolated copy to a previous recorded application version, checks health/data/model behavior, then returns it to its starting candidate. It does not replace the database during either switch.

The controller's mutation scope is fixed to Compose project `ain-rollback-drill`, loopback port 8091 and named volume `ain-rollback-drill_state`. The main `ain-local-release` project on 8090 is not a rollback target. Capturing its current image IDs is read-only. The dashboard displays a separate dated drill receipt rather than claiming the main deployment was rolled back or is production-qualified.

## Compatibility and safety boundary

The controller requires both API and web images to be present locally by immutable image ID, with matching source-revision labels. It does not pull images or rebuild while switching. The target must have the same database schema and identical canonical UTF-8/LF fingerprints for the selected prediction, queue, agent, index and recovery state-contract modules. Any mismatch blocks the drill. These conservative checks qualify only a narrow pair; matching fingerprints do not prove arbitrary releases are compatible or trustworthy. Use only retained images built from reviewed project source. Local records and image labels are not signed build attestations.

Waiting/running investigations block changes. The isolated drill disables its background worker and must not be used interactively during testing. It verifies its own named-volume mount and refuses the primary volume or a host bind mount at the state location. The web container is stopped for switching, so this is not a zero-downtime release. No application/schema migrations, model/prompt replacements, infrastructure rollback or database downgrade are attempted.

Across candidate → previous version → candidate, checks compare schema and table row counts, account-record fingerprints, active model and document-index hashes, and the exact historical research prediction. Docker image identities, container health/isolation and database-backed readiness are checked. Account fingerprints are used internally and omitted from the public receipt. This is selected state reconciliation, not an immutable audit or a byte-for-byte database-file comparison.

If target startup/verification fails, the controller always attempts to restore the starting candidate images on the isolated volume. It records no successful drill receipt unless all checks pass. Recovery of that candidate can itself fail; then the operator must investigate the isolated deployment. The primary project remains outside the controller's mutation scope. There is no automatic rollback service watching production deployments.

## Operator workflow

Run commands from the checkout using its Python environment and Docker Desktop. Keep a trusted private snapshot, sufficient free disk space and the known image pair. Never overwrite an existing key, backup, manifest, evidence output or restored data directory.

Capture the existing main version before building a candidate:

```powershell
python -m infra.releases capture --output .local/releases/prior.json
$env:AIN_RELEASE_TAG = 'rollback-candidate'
$env:AIN_RELEASE_REVISION = (git rev-parse HEAD).Trim()
# Use a clean, reviewed committed candidate distinct from the captured prior version.
docker compose build api web
$api = (docker image inspect ain-api:rollback-candidate | ConvertFrom-Json).Id
$web = (docker image inspect ain-web:rollback-candidate | ConvertFrom-Json).Id
python -m infra.releases inspect --api-image $api --web-image $web --output .local/releases/candidate.json
python -m infra.releases prepare --current .local/releases/candidate.json --output .local/releases/prepared.json
```

The prepare step writes the controller's private fixed Compose override. Restore a trusted snapshot into a **fresh** drill volume using the [recovery runbook](LOCAL_DEPLOYMENT_RECOVERY.md), substituting project `ain-rollback-drill` and the override below. Refuse an existing drill volume; do not delete it to force a rerun. The example assumes that explicitly named volume has never been initialized:

```powershell
$env:AIN_WEB_PORT = '8091'
$snapshot = (Resolve-Path .local/recovery/backups/my-snapshot).Path
docker compose -p ain-rollback-drill -f compose.yaml -f .local/releases/rollback-drill.override.json run --rm --no-deps --volume "${snapshot}:/restore:ro" api python -m infra.recovery restore --source /restore --destination /app/.local/active
docker compose -p ain-rollback-drill -f compose.yaml -f .local/releases/rollback-drill.override.json up -d --no-build --pull never --wait --wait-timeout 90 api web
python -m infra.releases drill --current .local/releases/candidate.json --target .local/releases/prior.json --output .local/releases/drill-result.json
```

Read the output and investigate any failure before retrying. This tool uses fixed local filenames/project names for the drill and is not a multi-environment release manager. Do not run concurrent controller operations or edit its override while it is active. The source snapshot contains private account hashes/history and is unencrypted unless separately sealed. It remains excluded from Git. The drill volume and local images are retained; no pruning, recursive cleanup, volume deletion or retention automation is provided. Stop only the explicitly named drill services when finished:

```powershell
docker compose -p ain-rollback-drill -f compose.yaml -f .local/releases/rollback-drill.override.json stop api web
```

Afterward clear task-specific environment overrides before ordinary main-project builds. Using the standard main dashboard does not require any of these operator commands.

## Evidence and limits

Measured results are recorded separately in [the drill report](reports/Local_Release_Rollback.json). The complete Windows suite has **156 tests: 129 Python and 27 Node**; Linux explicitly skips the Windows DPAPI provider case. Tests cover immutable IDs, compatibility gates, unsafe volume rejection, state mismatch, failed-target candidate recovery, receipt sanitization and UI qualification boundaries.

The isolated worker is disabled, so this drill does not establish worker recovery under load. The same model/index stay in place; model and prompt rollback remain unimplemented. Cloud deployment, managed TLS/identity, off-site/key recovery, independent observability, operational approval and full production release acceptance remain incomplete.

Later scoped-route agent changes alter protected runtime contracts. Older captured manifests may now be rejected by compatibility checks; this historical drill does not qualify rollback of that newer release. Review and re-drill the exact intended pair before claiming compatibility.

Synthetic gate review extends protected compatibility contracts to optimization/gates.py, optimization/history.py and optimization/reviews.py. Older manifests with the previous contract set are rejected. This preserves conservative compatibility checks; the historical drill does not qualify this new release. See GATE_PROPOSAL_REVIEW.md.

Current receipt binding and operator-only publication are described in [Rollback build evidence](ROLLBACK_BUILD_EVIDENCE.md). Version-2 drills require full committed source revisions. The measured report linked above remains historical; newer runtime receipts are retained outside Git and checked against the running candidate.
