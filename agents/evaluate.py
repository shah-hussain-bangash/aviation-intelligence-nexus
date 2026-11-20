"""Repeatable actual-model engineering cases with explicit acceptance checks."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4
from agents.runtime import Investigation, Investigator
from agents.store import AgentStore
from agents.quality import assess_report
from rag.index import ROOT
from rag.service import Knowledge
from services.api.main import initialize


def checks_for(case,run,replayed):
    checks={'scope_preserved':run['research_only'] is True and run['operational_approval'] is False,
        'tool_limit':len(run['steps'])<=3,
        'tools_allowlisted':all(step['tool'] in {'flight_metrics','knowledge_search','gate_simulation'} for step in run['steps']),
        'permission_preserved':case['include_simulation'] or all(step['tool']!='gate_simulation' for step in run['steps']),
        'retry_replayed_without_new_run':replayed.get('replayed') is True and replayed['run_id']==run['run_id']}
    quality=assess_report(run)
    if case['expect']=='coverage': checks['coverage_gate_passed']=quality['passed']
    if case['expect']=='abstention': checks['no_accepted_answer']=not run['claims'] and not quality['passed']
    if 'expected_records' in case:
        metrics=next((s.get('observation',{}) for s in run['steps'] if s['tool']=='flight_metrics'),{})
        checks['measured_record_count']=metrics.get('records')==case['expected_records']
    if 'expected_synthetic_assigned' in case:
        simulation=next((s.get('observation',{}) for s in run['steps'] if s['tool']=='gate_simulation'),{})
        checks['separate_verified_simulation']=simulation.get('data_kind')=='synthetic' and simulation.get('result',{}).get('candidate',{}).get('verification',{}).get('assigned')==case['expected_synthetic_assigned']
    if 'expected_document' in case:
        matches=[(s['id'],row['text']) for s in run['steps'] for row in s.get('observation',{}).get('evidence',[]) if row['source']==case['expected_document']]
        checks['relevant_document_retrieved']=bool(matches)
        checks['finding_from_expected_document']=any(c['citation']==identifier and c['quote'] in text and any(term in c['quote'].lower() for term in case['expected_quote_terms']) for c in run['claims'] for identifier,text in matches)
    return checks


def evaluate(case_id=None):
    path=ROOT/'agents/evaluation_cases.json';raw=path.read_bytes();contract=json.loads(raw)
    database=ROOT/'.local/agent-evaluation.sqlite3';initialize(database)
    runtime=Investigator(ROOT/'.local/ain.sqlite3',Knowledge(),AgentStore(database))
    user={'id':'engineering-evaluation','username':'engineering-evaluation','role':'admin'}
    rows=[]
    for case in contract['cases']:
        if case_id and case['id']!=case_id: continue
        request=Investigation(**{key:case[key] for key in ('objective','month','required_tools','include_simulation')})
        key=str(uuid4());started=time.monotonic();run=runtime.run(user,key,request);elapsed=round((time.monotonic()-started)*1000,2)
        replayed=runtime.run(user,key,request);checks=checks_for(case,run,replayed)
        row={'case':case['id'],'expect':case['expect'],'passed':all(checks.values()),'checks':checks,
            'state':run['state'],'quality':assess_report(run),'repair':run.get('report_repair'),
            'tools':[{'id':s['id'],'tool':s['tool'],'state':s['state']} for s in run['steps']],
            'claims':run['claims'],'rejected_claims':run.get('rejected_claims',0),'model':run.get('model'),
            'elapsed_ms':elapsed,'report_sha256':run.get('report_sha256')}
        rows.append(row);print(json.dumps({'case':row['case'],'passed':row['passed'],'state':row['state'],'repair':row['repair']}),flush=True)
    if not rows: raise ValueError('No matching evaluation cases')
    report={'scope':contract['scope'],'contract_sha256':hashlib.sha256(raw).hexdigest(),'runtime':'bounded-ollama-tools-v2',
        'passed':sum(row['passed'] for row in rows),'total':len(rows),'cases':rows,
        'semantic_review':'Not a general semantic entailment or task-completeness score; expected-document checks are specific to these development cases.'}
    output=ROOT/'docs/reports'/('Agent_Quality_Evaluation.json' if not case_id else 'Agent_Quality_'+case_id+'.json')
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case');arguments=parser.parse_args()
    result=evaluate(arguments.case);print(json.dumps({'passed':result['passed'],'total':result['total']}))
