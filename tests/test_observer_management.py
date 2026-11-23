import base64
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell task-controller fixture')
class ObserverManagementTests(unittest.TestCase):
    def exercise(self, case):
        with tempfile.TemporaryDirectory() as directory:
            def quoted(value):
                return "'" + str(value).replace("'", "''") + "'"
            script = r'''
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile(SOURCE,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw $errors }
foreach ($fn in $ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)) { Invoke-Expression $fn.Extent.Text }
$observerRoot=FIXTURE
$observerDirectory=Join-Path $observerRoot 'observer'
$observerPython=Join-Path $observerRoot 'pythonw.exe'
$observerConsole=Join-Path $observerRoot 'python.exe'
$observerTaskName='AIN-Local-Observer-8090'
$observerArguments='trusted fixture command'
$observerDescription='trusted fixture description'
$observerTriggerId='AIN-Observer-Periodic-Recovery-v1'
[System.IO.Directory]::CreateDirectory($observerDirectory) | Out-Null
$global:fixtureCalls=[System.Collections.Generic.List[string]]::new()
$logon=[pscustomobject]@{Enabled=$true;Id='logon';CimClass=[pscustomobject]@{CimClassName='MSFT_TaskLogonTrigger'}}
$global:fixturePeriodic=[pscustomobject]@{Enabled=$true;Id=$observerTriggerId;CimClass=[pscustomobject]@{CimClassName='MSFT_TaskTimeTrigger'};Repetition=[pscustomobject]@{Interval='PT1M';Duration=''}}
$global:fixtureTask=[pscustomobject]@{TaskName=$observerTaskName;TaskPath='\';Description=$observerDescription;State='Running';Actions=@([pscustomobject]@{Execute=$observerPython;Arguments=$observerArguments;WorkingDirectory=$observerRoot});Settings=[pscustomobject]@{MultipleInstances='IgnoreNew'};Principal=[pscustomobject]@{RunLevel='Limited';LogonType='Interactive'};Triggers=@($logon,$global:fixturePeriodic)}
# All scheduler operations are mocks. No real scheduled task, account or service is touched.
function Get-ScheduledTask { param($TaskName) return $global:fixtureTask }
function Disable-ScheduledTask { param($TaskName) $global:fixtureCalls.Add('disable');$global:fixtureTask.State='Disabled' }
function Stop-ScheduledTask { param($TaskName) $global:fixtureCalls.Add('stop') }
function Enable-ScheduledTask { param($TaskName) $global:fixtureCalls.Add('enable') }
function Start-ScheduledTask { param($TaskName) $global:fixtureCalls.Add('start');$global:fixtureTask.State='Running' }
function Set-ScheduledTask { param($TaskName,$Trigger) $global:fixtureCalls.Add('set');$global:fixtureTask.Triggers=$Trigger }
function Backup-ObserverTask { $global:fixtureCalls.Add('backup') }
function New-ObserverPeriodicTrigger { return $global:fixturePeriodic }
function Read-ObserverHealth { return @{state='healthy';production_ready=$false} }
$stop=Join-Path $observerDirectory 'stop.request'
switch (CASE) {
 'identity' {
  $global:fixtureTask.Actions[0].Arguments='unrelated task'
  foreach ($action in @('Status','Install','Start','Stop')) {
   $rejected=$false;try { Invoke-ObserverAction $action | Out-Null } catch { $rejected=$true }
   if (-not $rejected) { throw 'Unexpected task accepted' }
  }
  if ($global:fixtureCalls.Count) { throw 'Unexpected mutation' }
 }
 'status' {
  $result=Invoke-ObserverAction 'Status'
  if ($result.task_state -ne 'Running' -or -not $result.periodic_recovery_configured -or $global:fixtureCalls.Count) { throw 'Status mutated or misreported task' }
 }
 'stop' {
  $result=Invoke-ObserverAction 'Stop'
  if (($global:fixtureCalls -join ',') -ne 'disable,stop' -or -not (Test-Path -LiteralPath $stop) -or $result.task_state -ne 'Disabled') { throw 'Stop did not disable before stopping' }
 }
 'start' {
  [System.IO.File]::WriteAllText($stop,'fixture stop');$global:fixtureTask.State='Disabled'
  $result=Invoke-ObserverAction 'Start'
  if (($global:fixtureCalls -join ',') -ne 'enable,start' -or (Test-Path -LiteralPath $stop) -or $result.task_state -ne 'Running') { throw 'Explicit resume failed' }
 }
 'idempotent' {
  Invoke-ObserverAction 'Install' | Out-Null
  if ($global:fixtureCalls.Count) { throw 'Existing complete running installation mutated' }
 }
 'upgrade' {
  $global:fixtureTask.Triggers=@($logon)
  $result=Invoke-ObserverAction 'Install'
  if (($global:fixtureCalls -join ',') -ne 'backup,set' -or -not $result.periodic_recovery_configured) { throw 'Upgrade failed to preserve backup or add periodic trigger' }
 }
 'respect_stop' {
  [System.IO.File]::WriteAllText($stop,'fixture stop');$global:fixtureTask.Triggers=@($logon)
  $rejected=$false;try { Invoke-ObserverAction 'Install' | Out-Null } catch { $rejected=$true }
  if (-not $rejected -or $global:fixtureCalls.Count) { throw 'Install ignored explicit stop request' }
 }
 default { throw 'Unknown fixture case' }
}
Write-Output 'Fixture passed; no real scheduler operations performed'
'''.replace('SOURCE', quoted(ROOT / 'scripts/manage-local-observer.ps1')).replace('FIXTURE', quoted(directory)).replace('CASE', quoted(case))
            encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_unrelated_task_before_any_action(self):self.exercise('identity')
    def test_status_is_read_only(self):self.exercise('status')
    def test_stop_disables_periodic_relaunch_first(self):self.exercise('stop')
    def test_start_explicitly_resumes(self):self.exercise('start')
    def test_install_is_idempotent(self):self.exercise('idempotent')
    def test_old_task_upgrade_preserves_backup(self):self.exercise('upgrade')
    def test_install_respects_explicit_stop(self):self.exercise('respect_stop')
