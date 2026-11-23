param([ValidateSet('Install','Status','Start','Stop')][string]$Action = 'Status')
$ErrorActionPreference = 'Stop'
$observerRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$observerPython = Join-Path $observerRoot '.venv\Scripts\pythonw.exe'
$observerConsole = Join-Path $observerRoot '.venv\Scripts\python.exe'
$observerDirectory = Join-Path $observerRoot '.local\observer'
$observerTaskName = 'AIN-Local-Observer-8090'
$observerArguments = '-m infra.local_observer run --directory "' + $observerDirectory + '" --port 8090'
$observerDescription = 'AIN local dashboard observer v1; loopback 8090 only; no external notifications.'
$observerTriggerId = 'AIN-Observer-Periodic-Recovery-v1'

function Assert-ObserverTask($task) {
    if ($null -eq $task -or $task.Description -ne $observerDescription -or $task.Actions.Count -ne 1 -or
        $task.Actions[0].Execute -ne $observerPython -or $task.Actions[0].Arguments -ne $observerArguments -or
        $task.Actions[0].WorkingDirectory -ne $observerRoot -or $task.Settings.MultipleInstances -ne 'IgnoreNew' -or
        $task.Principal.RunLevel -ne 'Limited' -or $task.Principal.LogonType -ne 'Interactive') {
        throw 'Unexpected observer task identity, privilege or duplicate-instance settings; nothing changed.'
    }
}

function Get-ObserverTriggers($task) {
    $logon = @($task.Triggers | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_TaskLogonTrigger' })
    $periodic = @($task.Triggers | Where-Object { $_.Id -eq $observerTriggerId -and $_.CimClass.CimClassName -eq 'MSFT_TaskTimeTrigger' })
    if ($logon.Count -ne 1 -or -not $logon[0].Enabled -or $periodic.Count -gt 1 -or
        $task.Triggers.Count -ne (1 + $periodic.Count)) { throw 'Unexpected observer task triggers; nothing changed.' }
    if ($periodic.Count -eq 1 -and (-not $periodic[0].Enabled -or
        [System.Xml.XmlConvert]::ToTimeSpan($periodic[0].Repetition.Interval).TotalSeconds -ne 60 -or
        -not [string]::IsNullOrEmpty($periodic[0].Repetition.Duration))) { throw 'Unexpected periodic recovery settings; nothing changed.' }
    return [pscustomobject]@{logon_configured=$true; periodic_configured=($periodic.Count -eq 1)}
}

function Read-ObserverHealth {
    if (-not (Test-Path -LiteralPath $observerConsole -PathType Leaf)) { throw 'Create the project Python environment first.' }
    $text = & $observerConsole -m infra.local_observer status --directory $observerDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Observer health could not be read.' }
    return ($text | ConvertFrom-Json)
}

function Get-ObserverReport($task) {
    Assert-ObserverTask $task
    $triggers = Get-ObserverTriggers $task
    return [ordered]@{task_name=$observerTaskName; task_state=([string]$task.State);
        logon_trigger_configured=$triggers.logon_configured; periodic_recovery_configured=$triggers.periodic_configured;
        health=(Read-ObserverHealth); external_alert_delivery=$false; production_ready=$false;
        qualification='Configuration and fresh local observations only; not proof of logon startup or off-host monitoring.'}
}

function Backup-ObserverTask {
    $directory = Join-Path $observerRoot '.local\observer-task-history'
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    $path = Join-Path $directory ([guid]::NewGuid().ToString('N') + '.xml')
    $xml = Export-ScheduledTask -TaskName $observerTaskName
    $stream = [System.IO.File]::Open($path,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
    try {
        $bytes = [System.Text.Encoding]::Unicode.GetBytes($xml)
        $stream.Write($bytes,0,$bytes.Length)
        $stream.Flush()
    } finally { $stream.Dispose() }
}

function New-ObserverPeriodicTrigger {
    $trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 1)
    $trigger.Id = $observerTriggerId
    return $trigger
}

function Invoke-ObserverAction($requested) {
    # A permission/query error must propagate; only a successful empty query means no task exists.
    $task = @(Get-ScheduledTask | Where-Object { $_.TaskName -eq $observerTaskName -and $_.TaskPath -eq '\' })
    if ($task.Count -gt 1) { throw 'Ambiguous observer task.' }
    if ($task.Count -eq 0) {
        if ($requested -eq 'Status') { return @{installed=$false; health=@{state='unknown'}; production_ready=$false} }
        if ($requested -ne 'Install') { throw 'Observer is not installed. Use Install first.' }
        if (-not (Test-Path -LiteralPath $observerPython -PathType Leaf)) { throw 'Create the project Python environment first.' }
        if (Test-Path -LiteralPath (Join-Path $observerDirectory 'stop.request')) { throw 'An explicit stop request exists; review it before installing.' }
        $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $command = New-ScheduledTaskAction -Execute $observerPython -Argument $observerArguments -WorkingDirectory $observerRoot
        $triggers = @((New-ScheduledTaskTrigger -AtLogOn -User $user), (New-ObserverPeriodicTrigger))
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden
        Register-ScheduledTask -TaskName $observerTaskName -InputObject (New-ScheduledTask -Action $command -Trigger $triggers -Principal $principal -Settings $settings -Description $observerDescription) | Out-Null
        $task = Get-ScheduledTask -TaskName $observerTaskName
    } else { $task = $task[0] }
    Assert-ObserverTask $task
    $triggers = Get-ObserverTriggers $task
    $stop = Join-Path $observerDirectory 'stop.request'
    if ($requested -eq 'Install' -and (Test-Path -LiteralPath $stop)) { throw 'An explicit stop request exists. Use Start to resume intentionally.' }
    if ($requested -eq 'Status') { return (Get-ObserverReport $task) }
    if ($requested -eq 'Stop') {
        # Disable first, so a periodic trigger cannot immediately undo the requested stop.
        Disable-ScheduledTask -TaskName $observerTaskName | Out-Null
        Stop-ScheduledTask -TaskName $observerTaskName
        [System.IO.Directory]::CreateDirectory($observerDirectory) | Out-Null
        if (-not (Test-Path -LiteralPath $stop)) { [System.IO.File]::WriteAllText($stop,'Explicit operator stop request.') }
        return (Get-ObserverReport (Get-ScheduledTask -TaskName $observerTaskName))
    }
    if ($requested -eq 'Install' -and -not $triggers.periodic_configured) {
        Backup-ObserverTask
        Set-ScheduledTask -TaskName $observerTaskName -Trigger @($task.Triggers + (New-ObserverPeriodicTrigger)) | Out-Null
    }
    if (Test-Path -LiteralPath $stop) {
        if ($requested -ne 'Start') { throw 'An explicit stop request exists. Use Start to resume intentionally.' }
        $item = Get-Item -LiteralPath $stop
        if ($item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe stop request file.' }
        Remove-Item -LiteralPath $stop
    }
    if ($requested -eq 'Start' -or $task.State -ne 'Running') {
        Enable-ScheduledTask -TaskName $observerTaskName | Out-Null
        Start-ScheduledTask -TaskName $observerTaskName
    }
    $deadline = (Get-Date).AddSeconds(40)
    do {
        $current = Get-ScheduledTask -TaskName $observerTaskName
        $report = Get-ObserverReport $current
        if ($current.State -eq 'Running' -and $report.health.state -eq 'healthy') { return $report }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw 'Task retained, but fresh healthy running status was not established within 40 seconds.'
}

Invoke-ObserverAction $Action | ConvertTo-Json -Depth 8 -Compress
