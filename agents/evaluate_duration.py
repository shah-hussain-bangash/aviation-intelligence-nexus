"""Actual local-model evidence-tool check in separate engineering state."""
import argparse
import json
from pathlib import Path
import time
from uuid import uuid4
from agents.runtime import Investigation,Investigator
from agents.store import AgentStore
from agents.duration_evidence import valid_observation
from agents.quality import assess_report
from services.api.main import initialize
from services.api.paths import ROOT

OBJECTIVE='Use duration_evidence to review the frozen negative duration-regression experiment. Include May RMSE/MAE versus the mean/median baselines, severe-delay errors, and the entire failed-check/non-deployment/already-inspected-release limitation. Use only recorded duration evidence; do not query SQL, documents or simulation, refit a model, invent causes or recommend operational action. Keep full April/May metrics as structured evidence.'


def evaluate(output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():raise ValueError('Choose a new private engineering directory under .local')
    output.mkdir(parents=True);database=output/'checkpoints.sqlite3';initialize(database)
    request=Investigation(objective=OBJECTIVE,include_duration_evidence=True,required_tools=['duration_evidence'])
    (output/'request.json').write_text(json.dumps(request.model_dump(),indent=2)+'\n',encoding='utf-8')
    runtime=Investigator(database,None,AgentStore(database));actor={'id':'engineering-duration','username':'engineering-duration','role':'researcher'}
    key=str(uuid4());started=time.perf_counter();run=runtime.run(actor,key,request);elapsed=round((time.perf_counter()-started)*1000,2)
    replay=runtime.run(actor,key,request);steps=[s for s in run['steps'] if s['tool']=='duration_evidence']
    checks={'required_tool_completed':len(steps)==1 and steps[0]['state']=='completed','canonical_snapshot_retained':len(steps)==1 and valid_observation(steps[0].get('observation')),
        'negative_result_preserved':len(steps)==1 and steps[0].get('observation',{}).get('snapshot',{}).get('evaluation',{}).get('research_check',{}).get('passed') is False,
        'mandatory_quotes_present':not assess_report(run)['duration_required_quotes_missing'],'coverage_passed':assess_report(run)['passed'],'within_tool_budget':len(run['steps'])<=3,
        'awaiting_human_review':run['state']=='awaiting_review' and not run['reviews'],
        'retry_replayed':replay.get('replayed') is True and replay['run_id']==run['run_id'],'operational_approval_false':run['operational_approval'] is False}
    result={'format':'ain-duration-agent-engineering-v1','scope':'Actual local Qwen3 direct runtime with separate engineering checkpoints; not an authenticated real-user browser execution or held-out evaluation',
        'elapsed_ms':elapsed,'checks':checks,'passed':all(checks.values()),'run':run,'production_ready':False}
    (output/'evaluation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);result=evaluate(parser.parse_args().output)
    print(json.dumps({k:result[k] for k in ['elapsed_ms','checks','passed']},indent=2));raise SystemExit(0 if result['passed'] else 1)
