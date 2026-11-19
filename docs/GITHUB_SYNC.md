# Daily GitHub synchronization

Requested schedule: **daily at 20:00 Asia/Dubai** through the local Codex automation attached to the working chat.

Repository: `https://github.com/zenithdevelopers7-source/aviation-intelligence-nexus.git`

The schedule is configured separately in Codex; this document is not a scheduler. The local checkout, Git authentication and execution environment must be available when the automation runs.

## Review policy

1. Check the repository, origin URL, current branch and working-tree state.
2. Stop if another operation is in progress, the branch is not `main`, there are staged user changes, conflicts, unexpected paths or uncertain credentials/personal data.
3. Fetch the remote without changing the working tree. Stop if the remote is ahead or histories diverge; do not auto-rebase, merge or stash.
4. Inspect the actual diff and eligible new files. Run `npm run sync:plan` and `npm run check`.
5. Stage only reviewed, explicit file paths. Never use an indiscriminate add of the whole working tree.
6. Create a concise commit describing the real change, then push `main` without force.
7. Verify the remote head matches the published local commit. If nothing changed and nothing is ahead, do nothing.

Existing local commits also require review before automatic publication. No commit is created merely to record daily activity. The automation synchronizes saved work; it does not invent project progress or perform development by itself.

## Exclusions

Raw datasets, archives, credentials, private keys, `.env` files, personal documents, local databases, logs and model checkpoints must not be automatically published. Report CSVs under `docs/reports` are permitted only after content review. Secret-pattern detection is a basic guard, not a guarantee that content is safe.

Future task-specific check commands must be added as real backend/model code is introduced. Frontend source checks do not validate production behavior.
