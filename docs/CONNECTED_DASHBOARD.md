# Connected historical research panel

The dashboard now includes a separate, collapsible **Connected research data** panel. It reads actual local database aggregates and the verified v2 model report, while the existing 64 workspaces retain their prototype records and interactions.

## Start locally

From the repository root, start the API in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn services.api.main:app --host 127.0.0.1 --port 8002
```

Start the dashboard in another terminal:

```powershell
npm.cmd run dev
```

Open http://127.0.0.1:8080 and use **Refresh data**. If either service is already running, use the existing instance; restart it after source changes. `PORT` selects an alternate dashboard port. `AIN_API_PORT` selects the dashboard proxy's backend port; default 8002. Direct file opening cannot provide the API connection.

## Implemented scope

- Read-only `GET /api/v1/research/summary` aggregates only BTS records, preventing synthetic fixtures from inflating the displayed count.
- Monthly flight, cancellation and diversion counts, source coverage and actual response timestamp.
- v2 model metrics compared against the same-period constant training-prior baseline, plus training/test counts, precision, recall and false-alert count.
- Artifact hash verification before using the locally generated model report. This is local integrity verification, not externally signed provenance.
- Explicit research-only and historical-data labels; prediction serving remains disabled.
- Same-origin local proxy with one fixed read-only route, timeout, no browser credential forwarding and safe unavailable response. No arbitrary URL proxy or CORS wildcard.
- Manual refresh with loading, unavailable and recovery states. Old figures are removed before a new request and stay hidden on failure. There is no claim of continuous polling or a live airline feed.
- Responsive layout, native collapse/expand control, table headers/captions and announced connection state.

Automated verification uses `python -m unittest discover -s tests -v` in the project environment, `node --test tests/test_dashboard.mjs` and `npm run check`. Browser verification covers actual counts/model results, mobile layout, backend stop/unavailable state and restart/recovery. These are local integration checks, not production acceptance.

This original integration milestone added no authentication, inference, cloud deployment, monitoring or recovery qualification. A subsequent bounded historical-scenario endpoint is documented in `RESEARCH_PREDICTION.md`; operational serving remains disabled. The historical completion report remains a dated baseline rather than being silently rewritten as production evidence.
