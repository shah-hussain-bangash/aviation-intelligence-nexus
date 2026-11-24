"""Persisted due-time and pause-policy demonstration using synthetic cases and a test clock."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4

from pipelines.synthetic_ingestion import create_case, enqueue, enable_schedule, jobs, pause_schedule, schedule_status, work_one, host, local
from pipelines.verify_import_safety import BASE, identity
from pipelines.verify_incremental_ingestion import state
from services.api.paths import ROOT

SOURCES = ('pipelines/synthetic_ingestion.py','pipelines/verify_retry_scheduling.py','pipelines/verify_incremental_ingestion.py')


def busy():
    error = sqlite3.OperationalError('synthetic busy fault')
    error.sqlite_errorcode = sqlite3.SQLITE_BUSY
    return error


def verify(directory):
    host(); directory = local(directory)
    context = identity()
    context['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory.mkdir(parents=True,exist_ok=False)
    report = {'format':'ain-retry-scheduling-drill-v1','checked_at':datetime.now(timezone.utc).isoformat(),
              'case_id':directory.name, **context,'passed':False,'checks':{},'synthetic_only':True,
              'clock':'explicit_test_epoch_seconds','busy_fault_injected':True,
              'background_scheduler_installed':False,'primary_database_accessed':False,
              'external_data_imported':False,'deployment_performed':False,'production_ready':False}
    try:
        case = create_case(directory/'scheduled')
        first = enqueue(case,BASE,year=2025,month=1)
        february = [*BASE[0]]; february[0] = '2025-02-01'
        second = enqueue(case,[february],year=2025,month=2)
        enabled = enable_schedule(case)
        with patch('pipelines.synthetic_ingestion.import_archive',side_effect=busy()):
            deferred = work_one(case,now=1000)
        observed = schedule_status(case,now=1000)
        other = work_one(case,now=1000)
        early = work_one(case,now=1029)
        child = subprocess.run([sys.executable,'-c',
            "import json,sys; from pipelines.synthetic_ingestion import schedule_status; print(json.dumps(schedule_status(sys.argv[1],now=1029)))",str(case)],
            cwd=ROOT,capture_output=True,text=True,timeout=30)
        independent = json.loads(child.stdout) if child.returncode == 0 else {}
        pause_schedule(case,True)
        paused = schedule_status(case,now=1030)
        held = work_one(case,now=1030)
        attempts_while_paused = jobs(case)[0]['attempts']
        pause_schedule(case,False)
        resumed = work_one(case,now=1030)
        exhausted = create_case(directory/'exhausted')
        enqueue(exhausted,BASE,year=2025,month=1); enable_schedule(exhausted)
        with patch('pipelines.synthetic_ingestion.import_archive',side_effect=busy()):
            a = work_one(exhausted,now=2000); due_a = jobs(exhausted)[0]['not_before']
            b = work_one(exhausted,now=2030); due_b = jobs(exhausted)[0]['not_before']
            c = work_one(exhausted,now=2090)
        interrupted = create_case(directory/'interrupted')
        enqueue(interrupted,BASE,year=2025,month=1); enable_schedule(interrupted)
        with patch('pipelines.synthetic_ingestion.import_archive',side_effect=KeyboardInterrupt):
            try:work_one(interrupted,now=3000)
            except KeyboardInterrupt:pass
        crash_tick = work_one(interrupted,now=3001)
        crash_due = jobs(interrupted)[0]['not_before']
        after_crash = work_one(interrupted,now=3031)
        report['checks'] = {
            'extension_enabled': enabled,
            'busy_attempt_deferred': deferred['job_id'] == first and deferred['state'] == 'queued' and observed['next_due_epoch'] == 0,
            'independent_due_job_processed': other['job_id'] == second and other['state'] == 'succeeded',
            'no_early_retry': early is None,
            'separate_process_observed_due_time': independent.get('next_due_epoch') == 1030 and independent.get('due') == 0,
            'pause_prevents_claim': paused['paused'] and paused['eligible'] == 0 and held is None and attempts_while_paused == 1,
            'resume_runs_at_due_boundary': resumed['state'] == 'succeeded' and resumed['attempts'] == 2,
            'exponential_delays_persisted': a['state'] == b['state'] == 'queued' and (due_a,due_b) == (2030,2090),
            'attempts_exhausted': c['state'] == 'quarantined' and c['reason'] == 'attempt_limit',
            'interrupted_job_waits_before_reclaim': crash_tick is None and crash_due == 3031,
            'interrupted_job_recovered_at_due': after_crash['state'] == 'succeeded' and after_crash['attempts'] == 2,
            'synthetic_counts_reconciled': state(case) == {'flights':4,'imports':2,'observed_bts':0},
            'source_unchanged': all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() == h for p,h in context['source_sha256'].items())}
        report.update(jobs=jobs(case),exhausted_jobs=jobs(exhausted),interrupted_jobs=jobs(interrupted),
                      counts=state(case),observations={'after_busy':observed,'independent':independent,'paused':paused,'busy_due_times':[due_a,due_b],'interrupted_due':crash_due})
        report['passed'] = all(report['checks'].values())
    except Exception:
        report['error'] = 'synthetic_retry_scheduling_check_failed'
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = verify(ROOT/'.local/retry-scheduling'/uuid4().hex)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 2)
