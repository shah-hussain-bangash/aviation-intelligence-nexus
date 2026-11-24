"""Bounded foreground execution for explicitly scheduled synthetic research cases."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
import time
from uuid import uuid4

from pipelines.synthetic_ingestion import case_path, jobs, local, schedule_status, work_one


def request_stop(directory):
    directory = case_path(directory)
    local(directory/'stop.request').write_text('stop\n', encoding='utf-8')


@contextmanager
def runner_lock(directory):
    path = local(directory/'runner.lock')
    with path.open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell() == 0:stream.write(b'0');stream.flush()
        stream.seek(0); acquired = False
        try:
            if os.name == 'nt':
                import msvcrt
                try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                except OSError:raise ValueError('synthetic_runner_busy') from None
            else:
                import fcntl
                try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                except OSError:raise ValueError('synthetic_runner_busy') from None
            acquired = True
            yield
        finally:
            if acquired:
                if os.name == 'nt':stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def run(directory, *, max_seconds=60, max_steps=10, poll_seconds=0.25):
    if type(max_seconds) is not int or not 1 <= max_seconds <= 300:
        raise ValueError('invalid_runner_duration')
    if type(max_steps) is not int or not 1 <= max_steps <= 100:
        raise ValueError('invalid_runner_step_limit')
    if type(poll_seconds) not in (int,float) or not math.isfinite(poll_seconds) or not 0.05 <= poll_seconds <= 5:
        raise ValueError('invalid_runner_poll_interval')
    directory = case_path(directory)
    schedule_status(directory)  # Explicit extension required; never enable it silently.
    status_file = local(directory/'runner-status.json')
    stop_file = local(directory/'stop.request')
    with runner_lock(directory):
        started = time.monotonic()
        result = {'format':'ain-synthetic-runner-v1','run_id':uuid4().hex,
                  'started_at':datetime.now(timezone.utc).isoformat(),'state':'running',
                  'max_seconds':max_seconds,'max_steps':max_steps,'poll_seconds':poll_seconds,
                  'work_results':[],'wait_cycles':0,'sleep_seconds_requested':0,
                  'synthetic_only':True,'background_service_installed':False,'production_ready':False}
        def record():
            result['checked_at'] = datetime.now(timezone.utc).isoformat()
            result['elapsed_seconds'] = round(time.monotonic()-started,6)
            temporary = local(directory/('runner-status-'+uuid4().hex+'.tmp'))
            temporary.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
            os.replace(temporary,status_file)
        record()
        try:
            while True:
                if stop_file.exists():result['state']='stopped';break
                if time.monotonic()-started >= max_seconds:result['state']='duration_limit';break
                if len(result['work_results']) >= max_steps:result['state']='step_limit';break
                status = schedule_status(directory)
                if status['paused']:result['state']='paused';break
                outcome = work_one(directory)
                if outcome is not None:
                    row = next(row for row in jobs(directory) if row['job_id'] == outcome['job_id'])
                    result['work_results'].append({**outcome,'not_before':row['not_before'],
                                                   'completed_at_epoch':int(time.time())})
                    record();continue
                pending = jobs(directory)
                if not any(row['state'] in ('queued','running') for row in pending):
                    result['state'] = 'needs_review' if any(row['state'] != 'succeeded' for row in pending) else 'drained'
                    break
                # Fixed bounded polling also sees stop/pause changes while a retry waits.
                remaining = max_seconds-(time.monotonic()-started)
                delay = min(poll_seconds,max(0,remaining))
                result['wait_cycles'] += 1
                result['sleep_seconds_requested'] += delay
                record()
                time.sleep(delay)
        except KeyboardInterrupt:
            result['state'] = 'interrupted'
        except Exception:
            result.update(state='failed',error='synthetic_runner_execution_failed')
        record()
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case',help='Previously created and explicitly scheduled synthetic case only')
    parser.add_argument('--max-seconds',type=int,default=60)
    parser.add_argument('--max-steps',type=int,default=10)
    args = parser.parse_args()
    try:result=run(args.case,max_seconds=args.max_seconds,max_steps=args.max_steps)
    except Exception:result={'state':'failed','error':'synthetic_runner_failed','production_ready':False}
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['state'] in ('drained','paused','stopped') else 2)
