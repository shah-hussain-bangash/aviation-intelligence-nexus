"""Fresh synthetic foreground-runner demonstration, including real waiting for a retry."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from pipelines.import_bts import import_archive
from pipelines.synthetic_ingestion import create_case, enqueue, enable_schedule, jobs, pause_schedule, host, local
from pipelines.run_synthetic_ingestion import run, request_stop
from pipelines.verify_import_safety import BASE, identity
from pipelines.verify_incremental_ingestion import state
from pipelines.verify_retry_scheduling import busy
from services.api.paths import ROOT

SOURCES = ('pipelines/run_synthetic_ingestion.py','pipelines/verify_ingestion_runner.py',
           'pipelines/synthetic_ingestion.py','pipelines/verify_incremental_ingestion.py','pipelines/verify_retry_scheduling.py')


def verify(directory):
    host(); directory=local(directory)
    context=identity()
    context['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory.mkdir(parents=True,exist_ok=False)
    report={'format':'ain-ingestion-runner-drill-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'case_id':directory.name,**context,'passed':False,'checks':{},'synthetic_only':True,
            'busy_fault_injected':True,'clock':'host_epoch_and_monotonic_duration',
            'background_service_installed':False,'primary_database_accessed':False,
            'deployment_performed':False,'production_ready':False}
    try:
        automatic=create_case(directory/'automatic')
        enqueue(automatic,BASE,year=2025,month=1); enable_schedule(automatic,base_delay_seconds=1)
        calls=[0]
        def once_busy(*args,**kwargs):
            calls[0]+=1
            if calls[0]==1:raise busy()
            return import_archive(*args,**kwargs)
        with patch('pipelines.synthetic_ingestion.import_archive',side_effect=once_busy):
            retried=run(automatic,max_seconds=10,max_steps=5,poll_seconds=0.05)
        paused_case=create_case(directory/'paused')
        enqueue(paused_case,BASE,year=2025,month=1); enable_schedule(paused_case)
        pause_schedule(paused_case,True)
        paused=run(paused_case,max_seconds=5)
        stopped_case=create_case(directory/'stopped')
        enqueue(stopped_case,BASE,year=2025,month=1); enable_schedule(stopped_case)
        request_stop(stopped_case)
        stopped=run(stopped_case,max_seconds=5)
        bounded=create_case(directory/'bounded')
        enqueue(bounded,BASE,year=2025,month=1)
        february=[*BASE[0]]; february[0]='2025-02-01'
        enqueue(bounded,[february],year=2025,month=2); enable_schedule(bounded)
        limited=run(bounded,max_seconds=5,max_steps=1)
        resumed=run(bounded,max_seconds=5,max_steps=5)
        observations=retried['work_results']
        report['checks']={
            'automatic_due_retry_drained':retried['state']=='drained' and calls[0]==2,
            'retry_outcomes_recorded':len(observations)==2 and [r['state'] for r in observations]==['queued','succeeded'],
            'retry_completion_not_before_due':observations[-1]['completed_at_epoch']>=observations[0]['not_before'],
            'attempts_bounded':jobs(automatic)[0]['attempts']==2,
            'pause_clean_exit':paused['state']=='paused' and jobs(paused_case)[0]['attempts']==0,
            'stop_clean_exit':stopped['state']=='stopped' and jobs(stopped_case)[0]['attempts']==0,
            'stop_request_retained':(stopped_case/'stop.request').exists(),
            'step_limit_preserves_pending_work':limited['state']=='step_limit' and len(limited['work_results'])==1,
            'next_invocation_drains_remaining':resumed['state']=='drained' and len(resumed['work_results'])==1,
            'synthetic_counts_reconciled':state(automatic)=={'flights':3,'imports':1,'observed_bts':0} and state(bounded)=={'flights':4,'imports':2,'observed_bts':0},
            'latest_status_matches_results':all(json.loads((case/'runner-status.json').read_text(encoding='utf-8'))==result for case,result in ((automatic,retried),(paused_case,paused),(stopped_case,stopped),(bounded,resumed))),
            'source_unchanged':all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest()==h for p,h in context['source_sha256'].items())}
        report.update(runs={'automatic':retried,'paused':paused,'stopped':stopped,'limited':limited,'resumed':resumed},
                      automatic_jobs=jobs(automatic),bounded_jobs=jobs(bounded))
        report['passed']=all(report['checks'].values())
    except Exception:
        report['error']='synthetic_runner_check_failed'
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=verify(ROOT/'.local/ingestion-runner'/uuid4().hex)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 2)
