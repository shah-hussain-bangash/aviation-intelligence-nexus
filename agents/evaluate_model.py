"""Actual local-model engineering check with separate checkpoints; no user session."""
import argparse
import json
from pathlib import Path
import time
from uuid import uuid4
from agents.runtime import Investigation, Investigator
from agents.store import AgentStore
from agents.quality import assess_report
from agents.model_evidence import valid_observation
from rag.service import Knowledge
from services.api.main import initialize
from services.api.paths import ROOT

OBJECTIVE='Use model_evidence to review the frozen delay-v2 model. Include May false alerts and calibration error, April-only input reliance, and the non-causal and non-operational limitations. Use only recorded model evidence; no monthly SQL metrics, document search or simulation is needed.'


def evaluate(output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():
        raise ValueError('Choose a new private experiment directory under .local')
    request=Investigation(objective=OBJECTIVE,include_model_evidence=True,required_tools=['model_evidence'])
    output.mkdir(parents=True)
    (output/'request.json').write_text(json.dumps(request.model_dump(),indent=2)+'\n',encoding='utf-8')
    database=output/'checkpoints.sqlite3';initialize(database)
    runtime=Investigator(database,Knowledge(),AgentStore(database))
    user={'id':'engineering-model-agent','username':'engineering-model-agent','role':'researcher'}
    key=str(uuid4());started=time.perf_counter()
    run=runtime.run(user,key,request)
    elapsed=round((time.perf_counter()-started)*1000,2)
    (output/'run.json').write_text(json.dumps(run,indent=2)+'\n',encoding='utf-8')
    replay=runtime.run(user,key,request)
    steps=[s for s in run['steps'] if s['tool']=='model_evidence']
    checks={'model_tool_completed':len(steps)==1 and steps[0]['state']=='completed',
        'saved_snapshot_valid':len(steps)==1 and valid_observation(steps[0].get('observation')),
        'coverage_passed':assess_report(run)['passed'],'max_three_tools':len(run['steps'])<=3,
        'awaiting_human_review':run['state']=='awaiting_review' and not run['reviews'],
        'retry_replayed':replay.get('replayed') is True and replay['run_id']==run['run_id'],
        'operational_approval_false':run['operational_approval'] is False}
    result={'format':'ain-model-agent-engineering-v1','scope':'Actual local-model direct runtime with separate private checkpoints; not a real-user authenticated browser run or held-out benchmark',
        'elapsed_ms':elapsed,'checks':checks,'passed':all(checks.values()),'run':run,'production_ready':False}
    (output/'evaluation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    result=evaluate(parser.parse_args().output)
    print(json.dumps({k:result[k] for k in ['elapsed_ms','checks','passed']},indent=2))
    raise SystemExit(0 if result['passed'] else 1)
