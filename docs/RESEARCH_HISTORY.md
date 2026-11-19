# Persistent research history

Successful research calculations are now saved in the local SQLite database and displayed under **Saved research history** in the connected dashboard. Earlier calculations performed before this feature are not reconstructed. The 2,835,101 imported flight records remain separate from research scenario runs.

## Stored evidence

Each record stores its UUID, UTC save time, validated input scenario, input hash, model version, artifact hash, probability and research warnings. Legacy records retain actor `anonymous_local`. New records store the authenticated username and owner ID; researchers/viewers can read their own records, while administrators can also review legacy records. The local database is excluded from GitHub. Inputs and results are not sent to an external model provider.

Schema migration 3 creates `research_runs` and its time index. Startup migrations now run inside an explicit transaction. Existing flight records, import provenance and prior schema versions are preserved. A successful response is returned only after its history record commits. Invalid inputs, failed inference and failed integrity checks create no successful-run record.

The optional `Idempotency-Key` header must be a UUID. Repeating a key with the same validated input returns the original saved result and `replayed: true`; repeating it with different inputs returns 409. Concurrent retries use a unique request key and a transaction so only one record commits. Browser submissions generate a fresh key for each new calculation. Aborting the browser request cannot cancel a database commit that has already completed; refresh history after uncertain outcomes. Replays are saved historical results, not new inference or new model verification.

## Dashboard behavior

- `GET /api/v1/research/history` returns the latest ten records, newest first.
- **Refresh history** reloads actual database records; failures show unavailable rather than a false empty list.
- **View saved result** restores its scenario inputs and shows the saved model output labelled as previously saved. It does not rerun the model.
- **Export latest runs (JSON)** downloads only the loaded latest ten records. It is not a full database backup.
- Editing restored inputs clears the displayed result. A new calculation records a new run.

The prediction route and fixed history route are available through the local dashboard proxy. Restart both local services after updates; use the existing dashboard URL at http://127.0.0.1:8080.

## Limits and checks

This is append-only through the provided API; it is **not tamper-proof auditing**. Anyone with local database access can change or remove rows. Local session authentication and owner-scoped permissions are now implemented; managed identity, cryptographic audit signing, retention service and protected backup remain incomplete. See `LOCAL_IDENTITY.md`. Do not expose these local services publicly.

Verification covers saved results across restart, version-2 migration preserving existing flights, concurrent duplicate requests, conflicting request keys, failed calculations, bounded history and escaped UI output. The Python and Node suites remain the reproducible checks; browser testing exercises save, review and JSON export. Production readiness remains false.
