"""Abrupt runner exit, orphaned-status inspection and replay-safe recovery in a fresh case."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
from uuid import uuid4

from pipelines.synthetic_ingestion import create_case, enqueue, enable_schedule, jobs, host, local
from pipelines.run_synthetic_ingestion import run
from pipelines.inspect_runner_status import inspect, timestamp
from pipelines.verify_import_safety import BASE, identity
from pipelines.verify_incremental_ingestion import state
from services.api.paths import ROOT

SOURCES=('pipelines/inspect_runner_status.py','pipelines/verify_runner_recovery.py',
         'pipelines/run_synthetic_ingestion.py','pipelines/synthetic_ingestion.py','pipelines/verify_incremental_ingestion.py')
CRASH='''import os,sys
from unittest.mock import patch
from pipelines.run_synthetic_ingestion import run
import pipelines.synthetic_ingestion as worker
original=worker.import_archive
def interrupted(*args,**kwargs):
    original(*args,**kwargs)
    os._exit(74)
with patch.object(worker,'import_archive',interrupted):
    run(sys.argv[1],max_seconds=10)
'''


def verify(directory):
    host();directory=local(directory)
    context=identity()
    context['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory.mkdir(parents=True,exist_ok=False)
    report={'format':'ain-runner-recovery-drill-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'case_id':directory.name,**context,'passed':False,'checks':{},'synthetic_only':True,
            'background_service_installed':False,'primary_database_accessed':False,
            'deployment_performed':False,'production_ready':False}
    try:
        case=create_case(directory/'research');enqueue(case,BASE,year=2025,month=1)
        enable_schedule(case,base_delay_seconds=1)
        crashed=subprocess.run([sys.executable,'-c',CRASH,str(case)],cwd=ROOT,capture_output=True,timeout=60)
        before=state(case); abandoned=jobs(case)
        data=(case/'runner-status.json').read_bytes()
        (directory/'orphaned-runner-status.json').write_bytes(data)
        snapshot=json.loads(data)
        checked=timestamp(snapshot['checked_at'])
        entries=sorted(p.name for p in case.iterdir())
        recent=inspect(case,now=checked,stale_after=60)
        stale=inspect(case,now=checked+61,stale_after=60)
        preserved=data==(case/'runner-status.json').read_bytes() and entries==sorted(p.name for p in case.iterdir())
        recovered=run(case,max_seconds=10,max_steps=5,poll_seconds=0.05)
        final=inspect(case)
        after=state(case)
        report['checks']={
            'actual_runner_process_exited':crashed.returncode==74,
            'data_committed_before_exit':before=={'flights':3,'imports':1,'observed_bts':0},
            'queue_acknowledgment_interrupted':abandoned[0]['state']=='running' and abandoned[0]['attempts']==1,
            'orphaned_status_was_running':snapshot['state']=='running',
            'recent_snapshot_not_liveness':recent['classification']=='recent_running_snapshot' and not recent['process_liveness_verified'],
            'stale_status_classified':stale['classification']=='stale_running_snapshot' and stale['clock_override'],
            'inspection_preserved_inputs':preserved,
            'runner_lock_released_by_process_exit':recovered['state']=='drained',
            'recovery_used_import_ledger':len(recovered['work_results'])==1 and recovered['work_results'][0]['import_status']=='already_imported',
            'no_duplicate_rows_or_imports':after==before and jobs(case)[0]['attempts']==2,
            'terminal_snapshot_not_queue_health':final['classification']=='recorded_terminal_snapshot' and not final['queue_state_verified'],
            'source_unchanged':all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest()==h for p,h in context['source_sha256'].items())}
        report.update(crash_exit_code=crashed.returncode,counts=after,recent_inspection=recent,
                      stale_inspection=stale,final_inspection=final,recovered_run=recovered,
                      orphaned_status_sha256=hashlib.sha256(data).hexdigest(),jobs=jobs(case))
        report['passed']=all(report['checks'].values())
    except Exception:report['error']='synthetic_runner_recovery_check_failed'
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=verify(ROOT/'.local/runner-recovery'/uuid4().hex)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 2)
