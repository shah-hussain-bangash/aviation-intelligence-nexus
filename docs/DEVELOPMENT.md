# Daily development and automated checks

## One command to start locally

After the project Python environment is installed, run from the repository root:

```powershell
npm.cmd run dev:all
```

This starts the API on 127.0.0.1:8002 and dashboard on 127.0.0.1:8080. Keep the terminal open. Ctrl+C stops only processes started by that launcher; it leaves reused services alone. The launcher checks service identities before reusing occupied ports and refuses unrelated or older services. It never searches for or kills another process by port. `PORT` and `AIN_API_PORT` select different valid local ports.

VS Code: **Terminal → Run Task → AIN: Start API and dashboard** provides the same launcher. The older **Start dashboard** task remains frontend-only.

## One command to test

```powershell
npm.cmd test
```

This runs source validation, 27 Node dashboard/proxy/startup tests and 129 Python backend/data/model/history/optimization/knowledge/agent/recovery/monitoring tests (Windows; Linux skips the Windows DPAPI provider case). It uses the project's `.venv` interpreter regardless of the terminal's active environment. To install it on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r services/api/requirements-lock.txt -r infra/requirements-lock.txt
```

On Linux, the environment interpreter is `.venv/bin/python`. Direct Python dependencies are also listed in `requirements.txt`; the full snapshot pins the current tested environment but has no package hashes and is not a supply-chain verification guarantee.

## GitHub checks

The **Project checks** workflow runs after pushes to main and pull requests. Its source/Node job runs on Linux. Python tests run independently on Linux and Windows with Python 3.14 and pinned dependencies. Each Python job includes `pip check`. Workflow permissions are read-only; checkout credentials are not persisted. No secrets, provider credentials, raw flight downloads or trained model files are required for these tests.

CI uses synthetic temporary fixtures to test behavior. It does not repeat the million-row model experiments or establish production suitability. Experiment metrics remain separately recorded in sanitized reports. A fresh clone does not contain this workstation's local database or trained artifacts; import and training are separate reproducible steps.

The GitHub sync policy now requires `npm test` before publication. A successful local test is not proof of a successful hosted run; check the actual commit's GitHub Actions results. Authentication, authorization, cloud deployment, monitoring and protected recovery remain separate outstanding work.

Connected research now requires local sign-in. Create your first administrator using `docs/LOCAL_IDENTITY.md`; CI uses isolated temporary accounts, never your real account.

Local container deployment and restoration are described in [the recovery runbook](LOCAL_DEPLOYMENT_RECOVERY.md). The workflow also builds fresh API/web images, verifies health and container settings, restarts the API and verifies again on Linux. It uses empty synthetic state, not the workstation backup or host Ollama.

The Docker API enables local monitoring. Native developers can set `AIN_MONITOR_ENABLED=1` before API startup. See [monitoring](LOCAL_MONITORING.md) for counters, persistence, freshness and permission boundaries.

Encrypted backups use a separate operator dependency snapshot and Windows key provider; the dashboard containers do not receive the key. See [encrypted recovery](ENCRYPTED_RECOVERY.md).

Readiness evidence fingerprints normalize UTF-8 text to LF line endings. When changing a referenced document/report, review its scope and update the readiness catalog deliberately; missing/changed evidence is withheld. See RELEASE_READINESS.md.

The combined launcher enables the local investigation worker by default for newly started APIs. Existing services must be restarted to load code/configuration changes. See BACKGROUND_INVESTIGATIONS.md for queue limits, cancellation and recovery semantics.

Pinned local rollback is an operator-only isolated drill, not a main-dashboard action. See LOCAL_RELEASE_ROLLBACK.md before using its fixed project/port and private manifests.
