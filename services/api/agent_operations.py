"""Read-only aggregate queue observations; no objectives, identities or model calls."""
from contextlib import closing
from datetime import datetime, timezone
import math
from pathlib import Path
import sqlite3
from threading import Lock
import time

LOCK=Lock()
STATES=('queued','running','awaiting_review','reviewed','needs_changes','failed','interrupted','cancelled','withdrawn')
TOOLS=('flight_metrics','knowledge_search','gate_simulation','route_history','model_evidence','distribution_evidence')
EXECUTION='local-background-queue-v1'


class OperationsUnavailable(RuntimeError):
    pass


def age_seconds(value,now):
    try:
        at=datetime.fromisoformat(value)
        if at.tzinfo is None:return None
        age=(now-at).total_seconds()
        return round(age,2) if math.isfinite(age) and age>=0 else None
    except (TypeError,ValueError):return None


def snapshot(database,worker,now=None,clock=time.monotonic):
    if not LOCK.acquire(blocking=False):raise OperationsUnavailable('Operations snapshot busy')
    try:
        now=now or datetime.now(timezone.utc)
        if now.tzinfo is None:raise ValueError('An aware observation time is required')
        deadline=clock()+3
        database=Path(database).resolve()
        if not database.is_file():raise OperationsUnavailable('Queue storage unavailable')
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=.2)) as db:
            db.execute('PRAGMA query_only=ON')
            db.set_progress_handler(lambda: int(clock()>=deadline),1000)
            db.execute('BEGIN')
            totals={key:0 for key in (*STATES,'unknown')}
            for state,count in db.execute("SELECT json_extract(result_json,'$.state'),COUNT(*) FROM agent_runs WHERE json_extract(result_json,'$.execution')=? GROUP BY 1",(EXECUTION,)):
                totals[state if state in STATES else 'unknown']+=count
            active=db.execute("SELECT json_extract(result_json,'$.state'),json_extract(result_json,'$.created_at'),json_extract(result_json,'$.started_at') FROM agent_runs WHERE json_extract(result_json,'$.execution')=? AND json_extract(result_json,'$.state') IN ('queued','running') LIMIT 65",(EXECUTION,)).fetchall()
            if len(active)>64:raise ValueError('Active queue exceeds observation bound')
            # Extract only aggregate inputs. User/objective/arguments/claims never leave SQLite here.
            rows=db.execute("SELECT json_extract(result_json,'$.state'),json_type(result_json,'$.quality.passed'),json_type(result_json,'$.report_sha256'),(SELECT json_group_array(json_object('tool',json_extract(s.value,'$.tool'),'state',json_extract(s.value,'$.state'),'elapsed_ms',json_extract(s.value,'$.elapsed_ms'),'elapsed_type',json_type(s.value,'$.elapsed_ms'))) FROM json_each(agent_runs.result_json,'$.steps') AS s) FROM agent_runs WHERE json_extract(result_json,'$.execution')=? ORDER BY updated_at DESC,rowid DESC LIMIT 200",(EXECUTION,)).fetchall()
        import json
        tool_counts={key:{'attempted':0,'completed':0,'failed_or_unfinished':0} for key in (*TOOLS,'unknown')}
        coverage={'passed':0,'blocked':0,'not_recorded':0};durations=[];missing_tool_time=0
        for state,flag,report_type,steps_json in rows:
            if clock()>=deadline:raise OperationsUnavailable('Operations snapshot deadline exceeded')
            if state in ('awaiting_review','reviewed','needs_changes','withdrawn'):
                coverage['passed' if flag=='true' and report_type=='text' else 'blocked' if flag=='false' and report_type=='text' else 'not_recorded']+=1
            steps=json.loads(steps_json) if steps_json is not None else []
            if not isinstance(steps,list) or len(steps)>3:raise ValueError('Invalid saved tool steps')
            values=[]
            for step in steps:
                tool=step.get('tool');bucket=tool_counts[tool if tool in TOOLS else 'unknown'];bucket['attempted']+=1
                bucket['completed' if step.get('state')=='completed' else 'failed_or_unfinished']+=1
                elapsed=step.get('elapsed_ms')
                if step.get('elapsed_type') in ('integer','real') and type(elapsed) in (int,float) and math.isfinite(elapsed) and elapsed>=0:values.append(elapsed)
            if state in ('awaiting_review','reviewed','needs_changes','failed','interrupted','withdrawn'):
                if steps and len(values)==len(steps):durations.append(round(sum(values),2))
                else:missing_tool_time+=1
        waiting=[age_seconds(created,now) for state,created,started in active if state=='queued']
        running=[age_seconds(started,now) for state,created,started in active if state=='running']
        poll_age=age_seconds(worker.get('last_poll'),now)
        enabled=worker.get('enabled') is True;alive=worker.get('alive') is True;error=bool(worker.get('error'))
        worker_state='disabled' if not enabled else 'unavailable' if not alive or error else 'active' if totals['running'] else 'idle' if poll_age is not None and poll_age<=5 else 'unknown'
        durations.sort()
        if clock()>=deadline:raise OperationsUnavailable('Operations snapshot deadline exceeded')
        return {'format':'ain-agent-operations-v1','checked_at':now.isoformat(),'production_ready':False,
            'external_alert_delivery':False,'scope':'Current saved local background queue; synchronous engineering runs excluded',
            'totals':totals,'total_background_runs':sum(totals.values()),
            'active_ages':{'oldest_wait_seconds':max((v for v in waiting if v is not None),default=None),
                'oldest_running_seconds':max((v for v in running if v is not None),default=None),
                'unknown_wait_times':waiting.count(None),'unknown_running_times':running.count(None)},
            'worker':{'state':worker_state,'enabled':enabled,'alive':alive,'poll_age_seconds':poll_age,'error_recorded':error},
            'recent_window':{'size':len(rows),'limit':200,'order':'Most recently updated; review updates can change window membership',
                'recorded_draft_coverage':coverage,'tools':tool_counts,
                'tool_time':{'sample_size':len(durations),'not_recorded':missing_tool_time,
                    'p50_ms':durations[math.ceil(.50*len(durations))-1] if durations else None,
                    'p95_ms':durations[math.ceil(.95*len(durations))-1] if durations else None,
                    'max_ms':durations[-1] if durations else None}},
            'limits':{'waiting':5,'per_owner_waiting':2,'running':1,'sql_deadline_seconds':3},
            'meaning':'Saved coverage flags are not recomputed or semantic accuracy. Tool time excludes queue waiting, model planning/generation and human review. Active age is not a cancellation deadline. Local observation only; no failover, external alerts or protected audit.'}
    except (OSError,sqlite3.Error,TypeError,ValueError,KeyError) as error:
        raise OperationsUnavailable('Operations snapshot could not be verified') from error
    finally:LOCK.release()
