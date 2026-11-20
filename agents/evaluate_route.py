"""Actual-model route engineering check with separate private checkpoints, not API authentication."""
import argparse
import json
from pathlib import Path
import time
from uuid import uuid4
from agents.runtime import Investigation, Investigator
from agents.store import AgentStore
from agents.quality import assess_report
from rag.service import Knowledge
from services.api.main import initialize
from services.api.paths import ROOT
from services.api.route_history import valid_saved_profile


def evaluate(database, output, origin='JFK', destination='LAX'):
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / '.local').resolve()) or output == (ROOT / '.local').resolve():
        raise ValueError('Use a new private experiment directory beneath .local')
    if output.exists():
        raise ValueError('Preserve existing engineering evidence and choose a new directory')
    request = Investigation(objective=f'Compare the explicitly selected {origin} to {destination} route across January-March and May 2025. Include observed cohort counts, delay rates, nominal Wilson intervals and their limitations. Use route history evidence; do not substitute monthly totals or simulation.',
        required_tools=['route_history'], route={'origin':origin,'destination':destination})
    if not Path(database).is_file():
        raise ValueError('The local historical source database is unavailable')
    output.mkdir(parents=True)
    (output / 'request.json').write_text(json.dumps(request.model_dump(),indent=2)+'\n',encoding='utf-8')
    checkpoints = output / 'checkpoints.sqlite3'
    initialize(checkpoints)
    runtime = Investigator(Path(database), Knowledge(), AgentStore(checkpoints))
    user = {'id':'engineering-route-agent','username':'engineering-route-agent','role':'researcher'}
    key = str(uuid4())
    started = time.perf_counter()
    run = runtime.run(user,key,request)
    (output / 'run.json').write_text(json.dumps(run,indent=2)+'\n',encoding='utf-8')
    elapsed = round((time.perf_counter()-started)*1000,2)
    replayed = runtime.run(user,key,request)
    steps = [step for step in run['steps'] if step['tool']=='route_history']
    checks = {'route_tool_completed':len(steps)==1 and steps[0]['state']=='completed',
        'max_three_tools':len(run['steps'])<=3,
        'route_profile_valid':len(steps)==1 and valid_saved_profile(steps[0].get('observation',{}).get('profile'),request.route.model_dump()),
        'mechanical_coverage_passed':assess_report(run)['passed'],
        'retry_replayed':replayed.get('replayed') is True and replayed['run_id']==run['run_id'],
        'operational_approval_false':run['operational_approval'] is False}
    report = {'format':'ain-route-agent-engineering-v1',
        'scope':'Actual local-model engineering run with read-only historical source and separate checkpoints; direct runtime, not a real-user authenticated browser run',
        'elapsed_ms':elapsed,'checks':checks,'run':run,'passed':all(checks.values()),'production_ready':False}
    (output / 'evaluation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=ROOT/'.local/ain.sqlite3')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--origin',default='JFK')
    parser.add_argument('--destination',default='LAX')
    args=parser.parse_args()
    result=evaluate(args.database,args.output,args.origin,args.destination)
    print(json.dumps({'passed':result['passed'],'checks':result['checks'],'state':result['run']['state'],'elapsed_ms':result['elapsed_ms']},indent=2))
    raise SystemExit(0 if result['passed'] else 1)
