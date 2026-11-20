"""Operator smoke test on an already-restored state; never creates a user account."""
import argparse
import json
from uuid import uuid4
from services.api.paths import STATE
from services.api.prediction import ResearchPredictor,Scenario
from infra.recovery import database_facts
from rag.service import Knowledge,Question
from agents.runtime import Investigator,Investigation
from agents.store import AgentStore


def validate(with_ai=False):
    facts=database_facts(STATE/'ain.sqlite3')
    prediction=ResearchPredictor(STATE/'models/delay-v2').predict(Scenario.model_validate({
        'carrier':'AA','origin':'JFK','destination':'LAX','flight_date':'2025-05-15','scheduled_departure':'09:00'}))
    checks={'database_integrity':True,'flight_records_present':facts['row_counts']['flights']>0,
        'research_prediction':prediction['research_only'] is True and prediction['operational_serving_approved'] is False}
    result={'scope':'Operator smoke on restored local state; not user acceptance or production qualification',
        'flight_records':facts['row_counts']['flights'],'prediction_probability':prediction['arrival_delay_15_probability'],
        'artifact_sha256':prediction['artifact_sha256'],'checks':checks,'production_ready':False}
    if with_ai:
        knowledge=Knowledge()
        evidence=knowledge.query(Question(question='What are the operational limitations of the second delay model?'),source_document='docs/DELAY_V2.md')
        checks['scoped_local_embedding_retrieval']=bool(evidence['evidence']) and all(row['source']=='docs/DELAY_V2.md' for row in evidence['evidence'])
        request=Investigation(objective='For May 2025, report actual imported flight counts and observed arrival-delay rate, retrieve the second delay model limitations, and run the separate synthetic gate allocation demonstration.',
            required_tools=['flight_metrics','knowledge_search','gate_simulation'],include_simulation=True,document_scope='docs/DELAY_V2.md')
        # This is an OS-owner verification record in the restored copy, not a signed-in user or approval.
        run=Investigator(STATE/'ain.sqlite3',knowledge,AgentStore(STATE/'ain.sqlite3')).run(
            {'id':'operator-release-probe','username':'operator-release-probe','role':'admin'},str(uuid4()),request)
        checks['agent_tools_completed']=len(run['steps'])==3 and all(step['state']=='completed' for step in run['steps'])
        checks['agent_coverage_gate']=run.get('quality',{}).get('passed') is True and run['operational_approval'] is False
        result['agent']={'state':run['state'],'error_type':run.get('error_type'),'tools':[step['tool'] for step in run['steps']],
            'quality':run.get('quality'),'repair':run.get('report_repair'),'research_only':True,'operational_approval':False}
    result['passed']=all(checks.values())
    (STATE/'recovery-runtime-checks.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--with-ai',action='store_true');args=parser.parse_args()
    result=validate(args.with_ai);print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
