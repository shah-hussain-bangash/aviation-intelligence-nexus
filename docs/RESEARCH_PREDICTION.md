# Historical scenario prediction

The connected dashboard now has a **Try a historical flight scenario** form backed by actual v2 inference. This is a local research demonstration, not an operational airline forecast.

Open http://127.0.0.1:8080 with the Python API on port 8002. Wait for the connected data panel, then scroll to the form. The provided AA / JFK / LAX / 2025-05-15 / 09:00 example produces approximately **14.4%** from the saved v2 model. This is a scenario estimate, not evidence an actual flight operated on that schedule, and not a new independent test result.

## Implemented behavior

- `POST /api/v1/research/predict` accepts only carrier, origin, destination, historical flight date and scheduled departure in local `HH:MM` time.
- Dates are restricted to January–May 2025. Airport and carrier values must be present in training vocabulary. Extra fields, invalid time/date and identical airports are rejected.
- The fixed local model artifact is hashed on every request and checked against its local report and passed research gate before inference. Failed checks return 503; unfamiliar inputs return 422 with no probability.
- The model is loaded from a fixed trusted local path, cached by verified digest and used for one inference at a time. No request selects a model path or uploads a model. Hash matching is local integrity checking, not a digital signature; a local administrator can still replace both files.
- Reported probability is conditional on a completed, non-diverted flight with observed arrival delay. It does not model cancellation, prove calibration for a particular flight or recommend an action.
- Responses include artifact/model identity, echoed scenario, research-only warning and training/validation/test-period context.
- The same-origin proxy allows only the exact POST route and JSON bodies up to 4 KiB; it does not forward browser credentials. This is not authentication or general abuse protection.
- Editing inputs or refreshing the connection clears old results and cancels the browser request. Failed requests never display a previous probability as a new answer.

Successful calculations now commit a local research-history record before returning a result; see `RESEARCH_HISTORY.md`. Imported flight rows are not modified. The v2 model and its May evaluation are unchanged. Operational serving remains disabled; the status separately declares the research scenario endpoint available. There is no cloud deployment, user authorization, rate-limit service, monitoring or recovery qualification. Keep both servers bound to loopback.

## Verification

Run the Python test suite in `.venv`, `node --test tests/test_dashboard.mjs` and `npm run check`. Tests cover model inference, unknown-code abstention, strict input validation, failed research checks, artifact corruption even after caching, proxy request limits and output escaping. Browser checks cover a successful real inference, input editing and unsupported-code rejection.

Validation method: [FastAPI request bodies](https://fastapi.tiangolo.com/tutorial/body/) and [field constraints](https://fastapi.tiangolo.com/tutorial/body-fields/).
