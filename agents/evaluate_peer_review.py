"""Authenticated HTTP check with disposable accounts and recorded evidence, no LLM."""
from contextlib import closing
import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import secrets
import sqlite3
from uuid import uuid4
from fastapi.testclient import TestClient
from agents.runtime import Investigation
from agents.store import AgentStore,sha
from services.api.main import create_app
from services.api.paths import ROOT


def seed(store,owner,peer=True):
    source=json.loads((ROOT/'docs/reports/Distribution_Agent_Integration.json').read_text(encoding='utf-8'))['run']
    request=Investigation.model_validate({**source['request'],'require_peer_review':peer})
    result=store.begin(owner,str(uuid4()),request.model_dump())
    result.update(steps=copy.deepcopy(source['steps']),claims=copy.deepcopy(source['claims']),state='awaiting_review',
        evidence_origin='Recorded public evidence fixture; no provider execution in this workflow check',finding_style='verbatim_source_extracts')
    result['report_sha256']=sha({'request':result['request'],'steps':result['steps'],'claims':result['claims']});store.checkpoint(result)
    return result


def exercise(output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():raise ValueError('Choose a new private directory under .local')
    output.mkdir(parents=True);database=output/'fixture.sqlite3';app=create_app(database);password=secrets.token_urlsafe(24);origin={'Origin':'http://127.0.0.1:8080'}
    with TestClient(app) as client:
        for username,role in [('fixture-author','admin'),('fixture-reviewer','researcher'),('fixture-viewer','viewer')]:app.state.auth_store.create_user(username,password,role)
        with closing(sqlite3.connect(database)) as db:row=db.execute("SELECT id,username,role FROM auth_users WHERE username='fixture-author'").fetchone()
        owner=dict(zip(['id','username','role'],row));run=seed(AgentStore(database),owner);body={'run_id':run['run_id'],'report_sha256':run['report_sha256'],'decision':'reviewed','note':'Checked recorded counts, source limitations and research scope.'}
        def login(username):
            response=client.post('/api/v1/auth/login',json={'username':username,'password':password},headers=origin)
            if response.status_code!=200:raise RuntimeError('Fixture sign-in failed')
            return {**origin,'X-CSRF-Token':response.json()['csrf_token']}
        headers=login('fixture-author');pending=client.get('/api/v1/research/agent-jobs/'+run['run_id']).json()
        checks={'author_admin_self_review_blocked':client.post('/api/v1/research/agent-review',json=body,headers=headers).status_code==409}
        login('fixture-viewer');checks['viewer_inbox_denied']=client.get('/api/v1/research/agent-review-inbox').status_code==403;checks['viewer_shared_report_hidden']=client.get('/api/v1/research/agent-jobs/'+run['run_id']).status_code==404
        headers=login('fixture-reviewer');checks['pending_shared_listed']=client.get('/api/v1/research/agent-review-inbox').json()['runs'][0]['run_id']==run['run_id']
        peer_view=client.get('/api/v1/research/agent-jobs/'+run['run_id']).json();checks['different_account_can_review']=peer_view['review_access']['can_review'] is True
        checks['csrf_required']=client.post('/api/v1/research/agent-review',json=body,headers=origin).status_code==403
        response=client.post('/api/v1/research/agent-review',json=body,headers=headers);reviewed=response.json();checks['peer_review_saved']=response.status_code==200 and reviewed['state']=='reviewed' and reviewed['reviews'][0]['second_account_review'] is True
        checks['closed_removed_from_inbox']=client.get('/api/v1/research/agent-review-inbox').json()['runs']==[]
        checks['closed_peer_read_hidden']=client.get('/api/v1/research/agent-jobs/'+run['run_id']).status_code==404
        login('fixture-author');final=client.get('/api/v1/research/agent-jobs/'+run['run_id']).json();checks['author_sees_decision_no_operational_approval']=final['state']=='reviewed' and final['operational_approval'] is False
    result={'format':'ain-second-account-review-check-v1','checked_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Authenticated in-process HTTP with disposable accounts and a seeded recorded-evidence fixture; no new provider call, real-user review or operational approval',
        'checks':checks,'passed':all(checks.values()),'pending':pending,'peer_view':peer_view,'reviewed':reviewed,'production_ready':False}
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);result=exercise(parser.parse_args().output)
    print(json.dumps({'checks':result['checks'],'passed':result['passed']},indent=2));raise SystemExit(0 if result['passed'] else 1)
