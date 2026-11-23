# Daily GitHub synchronization

Requested schedule: **daily at 20:00 Asia/Dubai** through the local Codex automation attached to the working chat.

Repository: `https://github.com/shah-hussain-bangash/aviation-intelligence-nexus.git`

The schedule is configured separately in Codex; this document is not a scheduler. The local checkout, Git authentication and execution environment must be available when the automation runs.

On this workstation, authenticated Git operations run through the connected Desktop Commander device in the normal signed-in Windows session. This uses its existing protected Git Credential Manager login. A separate restricted execution account does not share that credential store. No token is copied into project files.

## Review policy

1. Check the repository, origin URL, current branch and working-tree state.
2. Stop if another operation is in progress, the branch is not `main`, there are staged user changes, conflicts, unexpected paths or uncertain credentials/personal data.
3. Fetch the remote without changing the working tree. Stop if the remote is ahead or histories diverge; do not auto-rebase, merge or stash.
4. Inspect the actual diff and eligible new files. Run `npm run sync:plan` and `npm test` (source, dashboard/proxy/startup and Python backend/model tests). Stop if the project Python environment or dependencies are unavailable; do not skip backend checks.
5. Stage only reviewed, explicit file paths. Never use an indiscriminate add of the whole working tree.
6. Create a concise commit describing the real change, then push `main` without force.
7. Verify the remote head matches the published local commit. If nothing changed and nothing is ahead, do nothing.

Existing local commits also require review before automatic publication. No commit is created merely to record daily activity. The automation synchronizes saved work; it does not invent project progress or perform development by itself.

## Exclusions

Raw datasets, archives, credentials, private keys, `.env` files, personal documents, local databases, logs and model checkpoints must not be automatically published. Report CSVs under `docs/reports` are permitted only after content review. Secret-pattern detection is a basic guard, not a guarantee that content is safe.

`npm test` now includes source validation, Node integration/startup tests and the Python suite. GitHub also runs Python tests on Linux and Windows using synthetic temporary test fixtures; raw datasets and model artifacts are not needed. These checks do not establish production behavior or airline model suitability.

The GitHub account was renamed to `shah-hussain-bangash`; repository ID 1463875455 is unchanged. Origin and the approved sync destination now use that canonical address. Historical evidence may retain redirected links under the former username. A disconnected Desktop Commander session still blocks scheduled authenticated sync; the account rename does not repair that connection.
