# Continuous local observer

`python -m infra.local_observer run --directory .local/observer --port 8090` runs a separate OS process that polls dashboard readiness and frontend liveness every five seconds. It needs no account, model access or Docker privileges. Approved targets are loopback ports 8090 (main dashboard) and 8092 (isolated drill). HTTP proxies and redirects are disabled; response size and request duration are bounded. A valid dashboard JSON identity is required, with explicit backend readiness for the API probe.

Only one observer may use a directory. Its OS file lock is released on normal exit or process termination. A process restart starts a new monitoring instance; it does not reuse earlier health or claim uninterrupted history. The existing monitor retains at most 50 component transitions in its current instance and writes its latest record atomically. A persistence failure exits the observer unsuccessfully. These local files are editable evidence, not protected auditing or durable incident storage.

Inspect current health with `python -m infra.local_observer status --directory .local/observer`. Missing, malformed, future-dated or samples at least 15 seconds old return `unknown`. A recently written file is a health observation, not proof that a supervisor will keep running. Slow sequential probes may cause conservative expiry. The observer does not restart application services.

Stop it gracefully by creating `.local/observer/stop.request`. The next loop exits within approximately five seconds plus any in-progress probes. Remove that request explicitly before starting again. Ctrl+C or ending its supervisor also stops the process. No credentials or request contents are recorded. No email, Slack, SMS or on-call notifications are sent.

A Windows task can supervise this command in the normal signed-in user's session. Run the repository commands below from a normal PowerShell terminal; they do not require an account password. `Install` registers a limited-privilege task with both a logon trigger and an indefinite one-minute periodic recovery trigger. Existing unrelated tasks are rejected. A known older AIN task is backed up privately before adding its missing periodic trigger. Existing task actions, accounts and application containers are not replaced. Adding this source does not install a task.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/manage-local-observer.ps1 -Action Install
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/manage-local-observer.ps1 -Action Status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/manage-local-observer.ps1 -Action Stop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/manage-local-observer.ps1 -Action Start
```

`Status` is read-only and distinguishes task state from fresh endpoint observations. `Stop` disables the scheduled task before stopping it, preventing the periodic trigger from immediately undoing the operator's request. `Start` explicitly clears only the ordinary stop-request file, enables the task and waits for fresh health. `Install` respects an existing stop request. Inspect the named task in Windows Task Scheduler for supervision diagnostics. Task definitions and observer records remain under `.local`, excluded from Git.

The one-minute trigger provides another launch opportunity after an exited process; it does not kill or repair a hung running process. The ignore-new-instance policy and OS lock prevent duplicate observers. A periodic trigger does not establish exact recovery latency or continuous availability. Windows Restart-on-Failure settings alone failed a workstation drill; manual recovery restored monitoring. A later drill with the periodic trigger configured observed a new healthy observer automatically, while status correctly expired during the gap. That drill did not identify which trigger fired, and it does not qualify Restart-on-Failure policy or logon startup. Detailed receipts remain private runtime evidence, not source-code guarantees.

A workstation that is off, asleep or logged out cannot provide independent availability monitoring. Logon startup still needs a runtime check. Off-host monitoring, external alert delivery, alert acknowledgement/escalation, high availability and production acceptance remain incomplete. All 24 production requirements remain open.
