# Start your saved Aviation dashboard

Open this project in Visual Studio Code. Select **Terminal > Run Task > AIN: Start saved Docker dashboard**. When the task reports that the dashboard is ready, open **http://127.0.0.1:8090** and sign in with your existing account.

The equivalent command in the project terminal is:

```powershell
npm.cmd start
```

This starts the existing Docker deployment. It is different from `npm.cmd run dev:all`, which starts the native development services on ports 8080 and 8002. The new task uses port 8090 and the saved container data volume. Docker Desktop must be installed and its engine must be running; the command must have normal access to Docker on this computer.

## What startup checks

If the local dashboard already returns its expected service identity, a ready backend and an explicit incomplete-production flag, the task reports that it is already running and makes no Docker changes. This is a liveness/readiness observation, not image provenance, model validation or a new rollback drill.

Otherwise it refuses an unrelated occupied port, inspects the existing API and web containers, and checks the exact primary project/service names. It requires the named `ain-local-release_state` API volume, expected state path, no API host port and a single dashboard binding on `127.0.0.1:8090`. Missing or unexpected saved deployments stop the task for operator review.

Only after those checks does it run Compose **start** for the existing API/web pair, wait for their health and check dashboard/backend readiness again. It never builds or pulls images, creates replacement containers, creates accounts, changes passwords, deletes a volume or starts the isolated rollback drill. It does not upgrade an older deployment to the current source checkout. Release updates remain a separate reviewed operation. The task checks volume identity, not its stored contents, account availability or model artifacts. It does not perform data recovery; existing API startup behavior still applies.

## If startup stops

| Message | Next action |
| --- | --- |
| Docker is unavailable or did not respond | Open Docker Desktop. Wait for **Engine running**, then rerun the task from your normal Windows terminal. |
| Port 8090 belongs to another service | Inspect that service yourself. Startup will not stop or replace it. |
| Saved deployment, data volume or binding is unexpected | Review the existing deployment and [recovery runbook](LOCAL_DEPLOYMENT_RECOVERY.md). Do not delete a volume or initialize a new empty one to bypass the check. |
| Readiness could not be verified | Inspect the **ain-local-release** API/web health and logs in Docker Desktop. The task does not claim success. |

Closing the successful startup terminal leaves the Docker services running. Stop them deliberately in Docker Desktop when needed. Preserve their data volume.

## Verification scope

Six new Node tests exercise already-running reuse without Docker calls; occupied-port refusal; wrong volume/project/path/binding rejection; exact existing-pair startup; failed readiness/engine errors; and readiness identity/qualification checks. The existing three native-startup tests remain intact. On this workstation, the real already-running branch was exercised successfully. The stopped-container branch uses synthetic inspect fixtures and a mocked Docker command; it has not been exercised by stopping the user's running deployment.

All production requirements remain open. This host-side launcher adds no production certification, auto-updater, scheduled boot service or unattended credential handling.
