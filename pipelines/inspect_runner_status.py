"""Read-only bounded runner snapshot inspection; never asserts process liveness."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
import stat
import time

from pipelines.synthetic_ingestion import case_path, local, MAX_EPOCH

MAX_BYTES = 128*1024
STATES = {'running','drained','needs_review','paused','stopped','duration_limit','step_limit','interrupted','failed'}
FIELDS = {'format','run_id','started_at','state','max_seconds','max_steps','poll_seconds','work_results',
          'wait_cycles','sleep_seconds_requested','synthetic_only','background_service_installed',
          'production_ready','checked_at','elapsed_seconds'}


def require(condition):
    if not condition:raise ValueError('invalid_status')


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result); result[key]=value
    return result


def finite(value):
    return type(value) in (int,float) and -1e308 <= value <= 1e308 and math.isfinite(value)


def reject_constant(token):
    raise ValueError('nonfinite_json')


def timestamp(value):
    require(isinstance(value,str) and len(value)<=40)
    parsed=datetime.fromisoformat(value)
    require(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds()==0)
    return parsed.timestamp()


def validate(value):
    require(type(value) is dict and set(value) in (FIELDS,FIELDS|{'error'}))
    require(value['format']=='ain-synthetic-runner-v1' and value['state'] in STATES)
    require(isinstance(value['run_id'],str) and re.fullmatch('[0-9a-f]{32}',value['run_id']))
    require(value['synthetic_only'] is True and value['background_service_installed'] is False and value['production_ready'] is False)
    require(type(value['max_seconds']) is int and 1<=value['max_seconds']<=300)
    require(type(value['max_steps']) is int and 1<=value['max_steps']<=100)
    require(finite(value['poll_seconds']) and 0.05<=value['poll_seconds']<=5)
    require(type(value['wait_cycles']) is int and value['wait_cycles']>=0)
    require(finite(value['elapsed_seconds']) and value['elapsed_seconds']>=0)
    require(finite(value['sleep_seconds_requested']) and value['sleep_seconds_requested']>=0)
    start,checked=timestamp(value['started_at']),timestamp(value['checked_at'])
    require(checked>=start)
    require(type(value['work_results']) is list and len(value['work_results'])<=value['max_steps'])
    for row in value['work_results']:
        mandatory={'job_id','state','reason','not_before','completed_at_epoch'}
        require(type(row) is dict and mandatory<=set(row)<=mandatory|{'attempts','import_status'})
        require(isinstance(row['job_id'],str) and re.fullmatch('[0-9a-f]{32}',row['job_id']))
        require(row['state'] in ('queued','succeeded','quarantined','blocked'))
        require(row['reason'] in (None,'attempt_limit','batch_or_artifact_rejected','database_busy','database_unavailable'))
        for field in ('not_before','completed_at_epoch'):
            require(type(row[field]) is int and 0<=row[field]<=MAX_EPOCH)
        if 'attempts' in row:require(type(row['attempts']) is int and 1<=row['attempts']<=3)
        if 'import_status' in row:require(row['import_status'] in (None,'imported','already_imported'))
    if 'error' in value:require(value['state']=='failed' and value['error']=='synthetic_runner_execution_failed')
    return checked


def inspect(directory, *, stale_after=60, now=None):
    report={'format':'ain-runner-snapshot-inspection-v1','classification':'unavailable',
            'process_liveness_verified':False,'queue_state_verified':False,'status_authenticated':False,
            'data_modified':False,'production_ready':False,'clock_override':now is not None}
    try:
        require(type(stale_after) is int and 1<=stale_after<=3600)
        observed=time.time() if now is None else now
        require(finite(observed) and 0<=observed<=MAX_EPOCH)
        directory=case_path(directory)
        path=local(directory/'runner-status.json')
        with path.open('rb') as stream:
            before=os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and 0<before.st_size<=MAX_BYTES)
            data=stream.read(MAX_BYTES+1)
            after=os.fstat(stream.fileno())
        identity=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)
        require(len(data)==before.st_size and identity(before)==identity(after)==identity(path.stat()))
        value=json.loads(data.decode('utf-8'),object_pairs_hook=unique,parse_constant=reject_constant)
        checked=validate(value)
        age=observed-checked
        require(age>=0)
        classification='recorded_terminal_snapshot'
        if value['state']=='running':
            classification='recent_running_snapshot' if age<=stale_after else 'stale_running_snapshot'
        report.update(classification=classification,recorded_state=value['state'],run_id=value['run_id'],
                      status_sha256=hashlib.sha256(data).hexdigest(),age_seconds=round(age,6),
                      stale_after_seconds=stale_after,fresh=age<=stale_after,work_result_count=len(value['work_results']),
                      observed_at=datetime.fromtimestamp(observed,timezone.utc).isoformat())
    except Exception:
        report['error']='runner_snapshot_unavailable_or_invalid'
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case');parser.add_argument('--stale-after',type=int,default=60)
    args=parser.parse_args();result=inspect(args.case,stale_after=args.stale_after)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['classification'] in ('recorded_terminal_snapshot','recent_running_snapshot') else 2)
