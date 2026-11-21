"""Disposable-account sharing withdrawal check; recorded evidence, no new LLM call."""
from contextlib import closing
from datetime import datetime,timezone
import json
from pathlib import Path
import secrets
import sqlite3
from uuid import uuid4
from fastapi.testclient import TestClient
from agents.evaluate_peer_review import seed
from agents.store import AgentStore
from services.api.main import create_app
from services.api.paths import ROOT


def exercise(output):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()) or output==(ROOT/'.local').resolve() or output.exists():raise ValueError('Choose a new private directory under .local')
    output.mkdir(parents=True);database=output/'fixture.sqlite3';app=create_app(database);password=secrets.token_urlsafe(24);origin={'Origin':'http://127.0.0.1:8080'}
    with TestClient(app) as client:
        for username,role in [('fixture-author','admin'),('fixture-reviewer','researcher')]:app.state.auth_store.create_user(username,password,role)
        with closing(sqlite3.connect(database)) as db:row=db.execute("SELECT id,username,role FROM auth_users WHERE username='fixture-author'").fetchone()
        owner=dict(zip(['id','username','role'],row));run=seed(AgentStore(database),owner)
        body={'run_id':run['run_id'],'report_sha256':run['report_sha256'],'withdrawal_key':str(uuid4()),'note':'End fixture sharing; preserve the recorded evidence.','acknowledged':True}
        def login(username):
            response=client.post('/api/v1/auth/login',json={'username':username,'password':password},headers=origin)
            if response.status_code!=200:raise RuntimeError('Fixture sign-in failed')
            return {**origin,'X-CSRF-Token':response.json()['csrf_token']}
        path='/api/v1/research/agent-withdraw-sharing';read='/api/v1/research/agent-jobs/'+run['run_id']
        checks={'anonymous_denied':client.post(path,json=body,headers=origin).status_code==401}
        headers=login('fixture-reviewer');peer=client.get(read).json()
        checks['peer_cannot_withdraw']=client.post(path,json=body,headers=headers).status_code==404 and peer['review_access']['can_withdraw'] is False
        headers=login('fixture-author');pending=client.get(read).json()
        checks['owner_control_available']=pending['review_access']['can_withdraw'] is True
        checks['csrf_required']=client.post(path,json=body,headers=origin).status_code==403
        checks['strict_confirmation']=client.post(path,json={**body,'acknowledged':'true'},headers=headers).status_code==422
        response=client.post(path,json=body,headers=headers);withdrawn=response.json()
        checks['withdrawal_saved']=response.status_code==200 and withdrawn['state']=='withdrawn'
        checks['evidence_preserved']=all(withdrawn[k]==pending[k] for k in ['request','steps','claims','report_sha256','reviews'])
        replay=client.post(path,json=body,headers=headers)
        checks['identical_retry_same_receipt']=replay.status_code==200 and replay.json()['withdrawal_replayed'] is True and replay.json()['sharing_withdrawal']==withdrawn['sharing_withdrawal']
        checks['changed_retry_conflicts']=client.post(path,json={**body,'note':'A different withdrawal reason.'},headers=headers).status_code==409
        checks['owner_can_read']=client.get(read).json()['state']=='withdrawn'
        login('fixture-reviewer');checks['peer_access_ends']=client.get(read).status_code==404 and client.get('/api/v1/research/agent-review-inbox').json()['runs']==[]
        checks['no_fake_review_or_operational_approval']=withdrawn['reviews']==[] and withdrawn['operational_approval'] is False
    result={'format':'ain-sharing-withdrawal-check-v1','checked_at':datetime.now(timezone.utc).isoformat(),
        'scope':'Authenticated in-process HTTP with disposable accounts and seeded recorded evidence; no new LLM call, real-user withdrawal, recalled copy or operational approval',
        'checks':checks,'passed':all(checks.values()),'pending':pending,'peer_view':peer,'withdrawn':withdrawn,'production_ready':False}
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);result=exercise(parser.parse_args().output)
    print(json.dumps({'checks':result['checks'],'passed':result['passed']},indent=2));raise SystemExit(0 if result['passed'] else 1)
