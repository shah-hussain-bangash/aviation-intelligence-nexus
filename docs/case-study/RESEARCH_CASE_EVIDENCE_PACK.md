# End-to-end research case evidence pack

Aviation Intelligence Nexus brings recorded historical analysis, a synthetic gate solve, and a human research decision into a versioned case. Use this pack to reproduce the walkthrough and explain the boundaries of each result. [Portal screenshots](../../README.md#running-portal)

| Stage | Observable evidence | Scope |
| --- | --- | --- |
| Sign in | The local workspace opens after authentication. An anonymous request for gate history receives a denial, and the viewer's calculate button is disabled. | Disposable local accounts and loopback services |
| Read historical reports | The browser renders the recorded BTS lineage audit and April delay-threshold analysis through the API. | Recorded research reports. No data collection or model training runs during the rehearsal. |
| Compute a gate proposal | The optimizer assigns all five synthetic flights. The greedy comparison assigns four. | One designed fictional scenario. No airport allocation occurs. |
| Record a research decision | The receipt binds the decision to the same saved proposal and its SHA-256 fingerprint. | A local research review. Self-review is permitted. |
| Build the case timeline | Open a case from a stored synthetic prediction, add an investigation note, refresh, and attach the reviewed gate proposal at version 3. | Pinned development revision `90bf6824f99811816356eb803e72e233fb590ac5`. The stored prediction is a fixture and this run performs no inference. |

## Reproduce the browser checks

The [GitHub Actions workflow](../../.github/workflows/checks.yml) runs the current revision's sign-in, evidence and gate checks on pushes to `main` and pull requests. It runs the case attachment workflow separately against the [pinned candidate](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/tree/90bf6824f99811816356eb803e72e233fb590ac5). Download `aviation-research-browser-evidence` from the corresponding run. Each JSON receipt records its tested revision, mode, timestamp and verified steps.

For a local run, install Node.js 24, use the project's Python environment, and run from the repository root:

```sh
python -m pip install -r services/api/requirements-lock.txt -r infra/requirements-lock.txt playwright==1.62.0
python -m playwright install chromium
python tests/browser/verify_research_portal.py --output /tmp/ain-browser-main.json
```

On Linux, use `python -m playwright install --with-deps chromium` if browser system dependencies are missing. To repeat the case mode, check out the pinned candidate separately and run the current branch's script with `--repository /path/to/case-checkout --case-workspace --output /tmp/ain-browser-case.json`. Choose a new output file per run. The harness creates its own accounts, ports and temporary SQLite databases and stops both local services on exit. [Browser test source](../../tests/browser/verify_research_portal.py)

## Read the underlying evidence

- [Historical data audit](../DATA_QUALITY_LINEAGE.md) and [delay-threshold decision analysis](../MODEL_DECISION_TRADEOFFS.md)
- [Gate optimization](../GATE_OPTIMIZATION.md) and [proposal review](../GATE_PROPOSAL_REVIEW.md)
- [Versioned research case workflow](https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/90bf6824f99811816356eb803e72e233fb590ac5/docs/RESEARCH_CASE_WORKFLOW.md)
- [Production readiness and evidence register](../enterprise-architecture/12-READINESS-AND-EVIDENCE-REGISTER.md)
