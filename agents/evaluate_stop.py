"""Actual local-provider cooperative-stop check using isolated engineering state."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Event
import time
from unittest.mock import patch
from uuid import uuid4
from agents.evaluate_model import OBJECTIVE
from agents.jobs import JobQueue
from agents.runtime import Investigation, Investigator
from agents.store import AgentStore, now
from rag import ollama
from services.api.main import initialize
from services.api.paths import ROOT


def evaluate(output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():
        raise ValueError('Choose a new private directory under .local')
    output.mkdir(parents=True)
    database=output/'checkpoints.sqlite3';initialize(database)
    store=AgentStore(database);queue=JobQueue(store);runtime=Investigator(database,None,store)
    actor={'id':'engineering-stop','username':'engineering-stop','role':'researcher'}
    request=Investigation(objective=OBJECTIVE,include_model_evidence=True,required_tools=['model_evidence'])
    key=str(uuid4());entered=Event();original=ollama.call;responses=[]
    def observed(route,payload=None,**kwargs):
        if route=='chat':entered.set()
        response=original(route,payload,**kwargs)
        if route=='chat':responses.append({'done':response.get('done'),'done_reason':response.get('done_reason')})
        return response
    started=time.perf_counter()
    with patch.object(ollama,'call',side_effect=observed),ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(runtime.run,actor,key,request)
        if not entered.wait(15):raise RuntimeError('No provider chat call began; inspect local provider availability')
        saved=store.recent(actor)[0];accepted=queue.cancel(actor,saved['run_id'])
        result=pending.result(timeout=65)
        replay=runtime.run(actor,key,request)
    checks={'request_acknowledged_while_running':accepted['state']=='running' and bool(accepted.get('cancel_requested_at')),
        'current_provider_call_returned_normally':len(responses)==1 and responses[0]=={'done':True,'done_reason':'stop'},
        'stopped_before_tools':result['state']=='cancelled' and not result['steps'],
        'no_reviewable_draft':not result['claims'] and 'report_sha256' not in result and not result['reviews'],
        'retry_replays_without_new_provider_call':replay.get('replayed') is True and replay['run_id']==result['run_id'] and len(responses)==1,
        'no_operational_approval':result['operational_approval'] is False}
    report={'format':'ain-cooperative-stop-engineering-v1','checked_at':now(),
        'scope':'One actual local Qwen3 planner call, separate engineering database, no real user session; not an interruption benchmark',
        'elapsed_ms':round((time.perf_counter()-started)*1000,2),'provider_responses':responses,'checks':checks,
        'passed':all(checks.values()),'run':result,'production_ready':False}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='run'},indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    report=evaluate(parser.parse_args().output)
    raise SystemExit(0 if report['passed'] else 1)
